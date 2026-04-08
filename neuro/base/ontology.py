import json
import os

from neuro.base import nfx
from neuro.base.schema import Metaproperties, OntologyNodeInfo, Violations


class Ontology:
    """Accessor for ontology operations on NeuroBase."""

    def __init__(self, nb):
        self._nb = nb

    def clear(self, confirm=False):
        """Delete all ontology nodes (including metaontology) and their relationships."""
        if not confirm:
            raise ValueError("Refusing to clear ontology without confirm=True")

        ontology_objects = json.loads(os.environ["ONTOLOGY_OBJECTS"])
        query = f"""
        MATCH (root:OntologyNode)
        WHERE root.label IN {list(ontology_objects)}
        MATCH (type)-[:SUBCLASS_OF*0..]->(root)
        MATCH (n)
        WHERE type.label IN labels(n) AND n.`neuro.id` IS NOT NULL
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

    def export_nfx(self, path, name="", description="", version=""):
        """Export all ontology instances to an NFX file.

        Fetches every node whose label is a subclass (via SUBCLASS_OF) of any
        root ontology type (OntologyNode, OntologyRelationship, OntologyProperty),
        together with all relationships between them.
        """
        ontology_objects = json.loads(os.environ["ONTOLOGY_OBJECTS"])
        node_query = f"""
        MATCH (root:OntologyNode)
        WHERE root.label IN {list(ontology_objects)}
        MATCH (type)-[:SUBCLASS_OF*0..]->(root)
        MATCH (n)
        WHERE type.label IN labels(n) AND n.`neuro.id` IS NOT NULL
        RETURN DISTINCT n.`neuro.id` as nid, labels(n) as labels, properties(n) as properties
        """
        nodes = self._nb.get_data(node_query)
        ids = [n["nid"] for n in nodes]

        rel_query = """
        MATCH (a)-[r]->(b)
        WHERE a.`neuro.id` IN $ids AND b.`neuro.id` IN $ids
        RETURN a.`neuro.id` as from, b.`neuro.id` as to,
               type(r) as type, properties(r) as properties
        """
        relationships = self._nb.get_data(rel_query, {"ids": ids})

        return nfx.write(path, nodes, relationships, name=name, description=description, version=version)


class ObjectValidator:
    """Validates an object to be inserted into NeuroBase."""

    def __init__(self, nb, o):
        self.nb = nb
        self.object = o
        self.violations = Violations()

    def get_violations(self):
        self.validate_labels()
        self.validate_properties()
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

