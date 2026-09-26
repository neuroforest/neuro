import json
import os

from neuro.base import nfx
from neuro.base.schema import Metaproperties, Metarelationships, OntologyNodeInfo, Violations
from neuro.utils import exceptions, terminal_components


class Ontology:
    """Accessor for ontology operations on NeuroBase."""

    def __init__(self, nb):
        self._nb = nb

    def count(self):
        """Count all ontology nodes."""
        ontology_objects = json.loads(os.environ["ONTOLOGY_OBJECTS"])
        query = f"""
        MATCH (root:OntologyNode)
        WHERE root.label IN {list(ontology_objects)}
        MATCH (type)-[:SUBCLASS_OF*0..]->(root)
        MATCH (n)
        WHERE type.label IN labels(n) AND n.nid IS NOT NULL
        RETURN count(DISTINCT n) AS count
        """
        result = self._nb.get_data(query)
        return result[0]["count"]

    def clear(self, confirm=False):
        """Delete all ontology nodes (including metaontology) and their relationships."""
        if not confirm:
            base_name = os.getenv("BASE_NAME")
            node_count = self.count()
            if not terminal_components.bool_prompt(f"Clear ontology in '{base_name}'? ({node_count} nodes)"):
                raise SystemExit("Aborting clear.")

        ontology_objects = json.loads(os.environ["ONTOLOGY_OBJECTS"])
        query = f"""
        MATCH (root:OntologyNode)
        WHERE root.label IN {list(ontology_objects)}
        MATCH (type)-[:SUBCLASS_OF*0..]->(root)
        MATCH (n)
        WHERE type.label IN labels(n) AND n.nid IS NOT NULL
        DETACH DELETE n
        """
        self._nb.run_query(query)

    def is_valid_node(self, node):
        """Validate a node against the ontology."""
        validator = ObjectValidator(self._nb, node)
        violations = validator.get_violations()
        return not bool(violations)

    def info(self, label):
        """Return an OntologyNodeInfo for the given label."""
        return OntologyNodeInfo(self._nb, label)

    # Knowledge modules anchor on `KnowledgeMetadata` but are otherwise the
    # same shape — `DEFINES` membership, `DEPENDS_ON` pins, the same header
    # properties — so one export path covers both. Leaving them out would
    # narrow what a base-wide export covers: the old sweep took every node
    # under the ontology roots regardless of which metadata defined it.
    def _metadata(self, name=""):
        """The metadata rows to export, one per module, ordered by name.

        Matching on `name` is case-insensitive so `-o Filesystem` and
        `-o filesystem` both resolve; an unknown name raises rather than
        exporting nothing.
        """
        rows = self._nb.get_data(
            """
            MATCH (m:OntologyMetadata|KnowledgeMetadata)
            WHERE $name = "" OR toLower(m.name) = toLower($name)
            RETURN m.nid AS nid, m.type AS type, m.name AS name,
                   m.version AS version, m.description AS description
            ORDER BY m.name
            """,
            {"name": name},
        )
        if name and not rows:
            raise exceptions.NoOntology(f"no module named {name!r} in this base")
        return rows

    def export_nfx(self, path, name=""):
        """Export one ontology per file, reconstructed from what defines it.

        With `name`, `path` is the file to write. Without it, `path` is a
        directory and every ontology in the base is written to
        `<name>.nfx` inside it — the base still comes out in one call, but as
        n valid modules rather than one document claiming to be a module it is
        not (issue #72).

        Each document is scoped by the metadata node: its nodes are that
        node's `DEFINES` targets, its relationships those whose *source* it
        defines — the same ownership rule `import_nfx` reconciles by — and its
        header, dependencies included, is read off the node itself.

        Two fidelity limits, both inherent:

        - `hash` is `sha256(validators.py)` and is not stored in the graph, so
          a re-exported dir-form plugin comes back without one and needs
          `ontology.rehash` before it would pass pre-commit.
        - dependency versions are the dependency's *current* version in this
          base, not necessarily the pin the source file recorded.

        So the export is faithful to the base, which is what it is for; it is
        not a way to recover a historical file. For the same reason, an export
        taken from a base built by `ontology.render` carries the `:Dependency`
        marker that task adds to dependency-provided nodes — base state, not a
        defect here.
        """
        targets = self._metadata(name)
        docs = []
        for meta in targets:
            nodes = self._nb.get_data(
                """
                MATCH (:OntologyMetadata|KnowledgeMetadata {nid: $nid})-[:DEFINES]->(n)
                RETURN DISTINCT n.nid AS nid, labels(n) AS labels,
                       properties(n) AS properties
                ORDER BY n.nid
                """,
                {"nid": meta["nid"]},
            )
            # An edge belongs to the module that is *allowed* to declare it,
            # which is not simply the owner of its source. A file may declare an
            # edge as long as one endpoint is its own and the other is reachable
            # through its dependencies, so a cross-module edge belongs to
            # whichever endpoint-owner has the other in its dependency closure —
            # exactly one can, since a dependency cycle is rejected at import.
            # Assigning by source instead puts an upward reference in the
            # dependency's own file, and that file then fails to import against
            # its declared dependencies (issue #72).
            relationships = self._nb.get_data(
                """
                MATCH (m:OntologyMetadata|KnowledgeMetadata {nid: $nid})
                      -[:DEPENDS_ON*0..]->(dep:OntologyMetadata|KnowledgeMetadata)
                WITH m, collect(DISTINCT dep) AS scope
                MATCH (a)-[r]->(b)
                WHERE a.nid IS NOT NULL AND b.nid IS NOT NULL
                  AND NOT (a:OntologyMetadata|KnowledgeMetadata)
                  AND NOT (b:OntologyMetadata|KnowledgeMetadata)
                  AND ((EXISTS { (m)-[:DEFINES]->(a) }
                        AND any(s IN scope WHERE EXISTS { (s)-[:DEFINES]->(b) }))
                    OR (EXISTS { (m)-[:DEFINES]->(b) }
                        AND any(s IN scope WHERE EXISTS { (s)-[:DEFINES]->(a) })))
                RETURN DISTINCT a.nid AS from, b.nid AS to, type(r) AS type,
                       properties(r) AS properties
                ORDER BY from, to, type
                """,
                {"nid": meta["nid"]},
            )
            dependencies = [
                f"{r['nid']}@{r['version']}" for r in self._nb.get_data(
                    """
                    MATCH (:OntologyMetadata|KnowledgeMetadata {nid: $nid})
                          -[:DEPENDS_ON]->(d:OntologyMetadata|KnowledgeMetadata)
                    RETURN d.nid AS nid, d.version AS version ORDER BY d.name
                    """,
                    {"nid": meta["nid"]},
                )
            ]
            doc = nfx.Nfx.from_dict({
                "type": meta["type"] or "", "nid": meta["nid"] or "",
                "version": meta["version"] or "", "name": meta["name"] or "",
                "description": meta["description"] or "",
                "dependencies": dependencies,
                "nodes": nfx.order_labels(nodes),
                "relationships": relationships,
            })
            # Write only what validates: a partial run should leave fewer
            # files, never an invalid one.
            violations = nfx.validate(doc)
            fatal = {k: v for k, v in violations.items()
                     if k in ("missing_required", "invalid_nids", "untaggable_name",
                              "duplicate_nids", "duplicate_relationships") and v}
            if fatal:
                raise exceptions.NfxViolation(
                    f"refusing to write {meta['name']}: {fatal}"
                )
            target = path if name else os.path.join(path, f"{meta['name']}.nfx")
            if not name:
                os.makedirs(path, exist_ok=True)
            nfx.write(target, doc)
            docs.append(doc)
        return docs[0] if name else docs


class ObjectValidator:
    """Validates an object to be inserted into NeuroBase."""

    def __init__(self, nb, o):
        self.nb = nb
        self.object = o
        self.violations = Violations()

    def get_violations(self, validate_relationships=False):
        self.validate_labels()
        self.validate_properties()
        if validate_relationships:
            self.validate_relationships()
        return self.violations

    def validate_label(self, label):
        query = """
        MATCH (n:OntologyNode {label: $label})
        RETURN n.label as label;
        """
        ontology_node = self.nb.get_data(query, parameters={"label": label})
        if not ontology_node:
            self.violations.undefined_labels.append(label)
        elif len(ontology_node) > 1:
            raise ValueError(f"Multiple ontology nodes found with label: {label}")
        else:
            pass

    def validate_labels(self):
        for label in self.object.labels:
            self.validate_label(label)

    def validate_properties(self):
        for label in self.object.labels:
            if label in self.violations.undefined_labels:
                continue
            metaproperties = Metaproperties.from_ontology(self.nb, label)
            self.violations = metaproperties.validate_properties(self.object.properties, self.violations)

    def validate_relationships(self):
        nid = self.object.properties.get("nid")
        if not nid:
            return
        for label in self.object.labels:
            if label in self.violations.undefined_labels:
                continue
            metarelationships = Metarelationships.from_ontology(self.nb, label)
            self.violations = metarelationships.validate_relationships(self.nb, nid, self.violations)

