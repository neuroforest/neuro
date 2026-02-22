from pathlib import Path

from neuro.base import nfx
from neuro.core import Node


class Metaontology:
    """Export/import the metaontology (node types, relationship types) as NFX."""

    LABELS = ["OntologyNode", "OntologyProperty", "OntologyRelationship"]
    RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "metaontology.nfx"

    def __init__(self, nb):
        self._nb = nb

    def export_nfx(self, path=None):
        """Export metaontology nodes and their relationships to an NFX file."""
        path = path or self.RESOURCE_PATH

        label_list = self.LABELS
        node_query = """
        MATCH (n)
        WHERE any(l IN $labels WHERE l IN labels(n))
          AND n.`neuro.id` IS NOT NULL
        RETURN n.`neuro.id` as nid, labels(n) as labels, properties(n) as properties
        """
        nodes = self._nb.get_data(node_query, {"labels": label_list})

        rel_query = """
        MATCH (n)
        WHERE any(l IN $labels WHERE l IN labels(n))
          AND n.`neuro.id` IS NOT NULL
        WITH collect(n.`neuro.id`) as ids
        MATCH (a)-[r]->(b)
        WHERE a.`neuro.id` IN ids AND b.`neuro.id` IN ids
        RETURN a.`neuro.id` as `from`, b.`neuro.id` as `to`,
               type(r) as type, properties(r) as properties
        """
        relationships = self._nb.get_data(rel_query, {"labels": label_list})

        return nfx.write(path, nodes, relationships)

    def import_nfx(self, path=None):
        """Import metaontology from an NFX file into the database."""
        path = path or self.RESOURCE_PATH
        data = nfx.read(path)

        for entry in data.get("nodes", []):
            node = Node(
                uuid=entry["nid"],
                labels=entry["labels"],
                properties=entry.get("properties", {}),
            )
            labels_str = ":".join(node.labels)
            query = f"""
            MERGE (n:{labels_str} {{`neuro.id`: $neuro_id}})
            SET n += $properties
            RETURN n
            """
            params = {"neuro_id": node.uuid, "properties": node.properties}
            self._nb.run_query(query, params)

        for rel in data.get("relationships", []):
            rel_type = rel["type"]
            query = f"""
            MATCH (a {{`neuro.id`: $from_id}})
            MATCH (b {{`neuro.id`: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            """
            params = {
                "from_id": rel["from"],
                "to_id": rel["to"],
                "properties": rel.get("properties", {}),
            }
            self._nb.run_query(query, params)
