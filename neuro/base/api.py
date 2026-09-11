import os
import sys
import logging

import neo4j

from neuro.utils import config, terminal_style
from neuro.base.accessors.metadata import MetadataAccessor
from neuro.base.accessors.nodes import NodeAccessor
from neuro.base.accessors.objects import ObjectAccessor
from neuro.base.accessors.tiddlers import TiddlerAccessor
from neuro.base.metaontology import Metaontology
from neuro.base.ontology import Ontology


class NeuroBase:
    """
    Simple, reusable Neo4j client wrapper.
    """
    def __init__(self, neo4j_uri=None, neo4j_user=None, neo4j_password=None, **driver_kwargs):
        uri = neo4j_uri or os.getenv("NEO4J_URI")
        user = neo4j_user or os.getenv("NEO4J_USER")
        password = neo4j_password or os.getenv("NEO4J_PASSWORD")
        self._uri = uri
        try:
            self.driver = neo4j.GraphDatabase.driver(uri, auth=(user, password), **driver_kwargs)
        except neo4j.exceptions.ConfigurationError:
            logging.error(f"Incorrect Neo4j parameters: {uri}")
            return

        # Accessors
        self.metaontology = Metaontology(self)
        self.ontology = Ontology(self)
        self.objects = ObjectAccessor(self)
        self.nodes = NodeAccessor(self)
        self.metadata = MetadataAccessor(self)
        self.tiddlers = TiddlerAccessor(self)

    def _verify_store_id(self):
        """Refuse to act on a base other than the one config names.

        BASE_NAME says which base we *mean*; NEO4J_URI decides which we
        *reach*. Nothing reconciles the two, so a stale ENV or an inherited
        default silently operates on the wrong base — a `clear` aimed at one
        base wiping another, reporting success either way.

        Neo4j's store id is intrinsic and unique per base, so pinning the
        expected value in config catches this client-side, without writing a
        marker into every base. Opt-in: unset NEO4J_STORE_ID means no check,
        so unpinned bases and first-time bootstraps behave exactly as before.
        """
        expected = os.getenv("NEO4J_STORE_ID")
        if not expected or not getattr(self, "driver", None):
            return
        try:
            with self.driver.session() as session:
                record = session.run("CALL db.info() YIELD id RETURN id").single()
        except Exception:  # unreachable/unauthorised is reported elsewhere
            return
        actual = record["id"] if record else None
        if actual and actual != expected:
            print(
                f"{terminal_style.FAIL} Refusing to use "
                f"{os.getenv('NEO4J_URI', '?')}: expected "
                f"{os.getenv('BASE_NAME', '?')} (store {expected[:8]}…) but "
                f"found store {actual[:8]}…",
                file=sys.stderr,
            )
            sys.exit(1)

    def __enter__(self):
        self._verify_store_id()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def run_query(self, query, parameters=None):
        """
        Run a Cypher query and return the result.
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters or {})
                return result
        except neo4j.exceptions.ServiceUnavailable:
            print(f"{terminal_style.FAIL} Neo4j unavailable at {self.driver._pool.address}")
            sys.exit(1)

    def get_data(self, query, parameters=None):
        """
        Run a Cypher query and return the data as a list of records.
        """
        logging.debug(f"NeuroBase.get_data query: {query}")
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters or {})
                records = [record.data() for record in result]
                return records
        except neo4j.exceptions.ServiceUnavailable:
            print(f"{terminal_style.FAIL} Neo4j unavailable at {self.driver._pool.address}")
            sys.exit(1)

    def count(self, label=None, **properties):
        """
        Count nodes in the database, optionally filtered by label and properties.
        """
        node = f"(n:{label})" if label else "(n)"
        conditions = []
        params = {}
        for key, value in properties.items():
            param_name = key.replace(".", "_")
            conditions.append(f"n.`{key}` = ${param_name}")
            params[param_name] = value
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"MATCH {node}{where} RETURN count(n) AS count"
        result = self.get_data(query, params)
        return result[0]["count"]

    def descendant_labels(self, label):
        """
        Every class label at or below `label` in the ontology hierarchy.

        Instances carry only their own leaf label, so `MATCH (n:PipelineRun)`
        matches nothing even though every `*Run` class subclasses it. Resolve
        the archetype to its concrete labels first:

            labels = nb.descendant_labels("PipelineRun")
            nb.get_data(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
                "RETURN n", {"labels": labels}
            )

        Returns `[label]` when the class has no subclasses, and `[]` when no
        such class is declared.
        """
        query = """
        MATCH (c:OntologyNode {label: $label})
        OPTIONAL MATCH (d:OntologyNode)-[:SUBCLASS_OF*]->(c)
        WITH c, collect(DISTINCT d.label) AS descendants
        RETURN descendants + [c.label] AS labels
        """
        result = self.get_data(query, {"label": label})
        return sorted(result[0]["labels"]) if result else []

    def _verify_declared_identity(self):
        """Refuse a destructive act on a base the config did not name.

        `_verify_store_id` proves the URI and the store agree, but an inherited
        environment carries both together, so a wrong base passes it. And a
        caller's `ENV != PRODUCTION` check reads a label any wrapper re-declares.
        What cannot be faked by inheritance is the env-file chain itself: if the
        live identity differs from what the files for this APP_NAME/ENV declare,
        the base was not configured here. `nte app.test` cleared the sirin
        production base exactly this way (INC-2026-007).
        """
        declared = config.declared_values()
        drift = config.identity_drift(declared)
        want_uri = declared.get("NEO4J_URI")
        if want_uri and self._uri != want_uri:
            drift["NEO4J_URI"] = (self._uri, want_uri)
        if drift:
            detail = "; ".join(f"{k}={live!r} (declared {want!r})"
                               for k, (live, want) in sorted(drift.items()))
            raise RuntimeError(
                f"Refusing to clear {self._uri}: base identity is not the one config "
                f"declares for {os.getenv('APP_NAME', '?')}/{os.getenv('ENV', '?')} — {detail}")

    def clear(self, confirm=False):
        if not confirm:
            raise ValueError("Refusing to clear database without confirm=True")
        self._verify_declared_identity()

        query = """
        MATCH (o)
        DETACH DELETE o;
        """
        self.run_query(query)

    def close(self):
        """
        Close the driver.
        """
        if self.driver:
            self.driver.close()
