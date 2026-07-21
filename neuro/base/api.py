import os
import sys
import logging

import neo4j

from neuro.utils import terminal_style
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

    def clear(self, confirm=False):
        if not confirm:
            raise ValueError("Refusing to clear database without confirm=True")

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
