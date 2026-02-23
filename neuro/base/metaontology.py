from pathlib import Path

from neuro.base import nfx
from neuro.core import Node


class Metaontology:
    """Export/import the metaontology (node types, relationship types) as NFX."""

    LABEL = "Metaontology"
    RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "metaontology.nfx"

    def __init__(self, nb):
        self._nb = nb

    def export_nfx(self, path=None):
        """Export metaontology nodes and their relationships to an NFX file."""
        path = path or self.RESOURCE_PATH

        query = """
        MATCH (n:Metaontology)-[r]-(m)
        WHERE n.`neuro.id` IS NOT NULL AND m.`neuro.id` IS NOT NULL
        WITH collect(DISTINCT {nid: n.`neuro.id`, labels: labels(n),
                 properties: apoc.map.removeKeys(properties(n), ['created', 'modified'])})
             + collect(DISTINCT {nid: m.`neuro.id`, labels: labels(m),
                 properties: apoc.map.removeKeys(properties(m), ['created', 'modified'])}) as allNodes,
             collect({from: startNode(r).`neuro.id`, to: endNode(r).`neuro.id`,
                 type: type(r), properties: properties(r)}) as relationships
        UNWIND allNodes as n
        WITH collect(DISTINCT n) as nodes, relationships
        RETURN nodes, relationships
        """
        result = self._nb.get_data(query)[0]

        return nfx.write(
            path, result["nodes"], result["relationships"],
            name="Metaontology"
        )

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
