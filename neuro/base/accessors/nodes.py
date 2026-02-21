import json

from neuro.core import Node
from neuro.base.accessors import Accessor


class NodeAccessor(Accessor):

    def get(self, neuro_id):
        query = """
        MATCH (ion:OntologyNode {label:"Node"})
        MATCH (on)-[:SUBCLASS_OF*0..]->(ion)
        WITH on.label as node_label

        MATCH (n)
        WHERE node_label in labels(n) AND n.`neuro.id` = $neuro_id
        RETURN n as properties, labels(n) as labels, n.`neuro.id` as uuid;
        """
        data = self._nb.get_data(query, {"neuro_id": neuro_id})
        if not data:
            raise ValueError(f"No node found with neuro.id: {neuro_id}")
        if len(data) > 1:
            raise ValueError(f"Multiple nodes found with neuro.id: {neuro_id}")
        d = data[0]
        return Node(uuid=d["uuid"], labels=d["labels"], properties=d["properties"])

    def put(self, node):
        """
        Save a Node to the database. Merges on neuro.id, sets labels and properties.
        :param node: Node
        """
        labels_str = ":".join(node.labels)
        query = f"""
        MERGE (n:{labels_str} {{`neuro.id`: $neuro_id}})
        SET n += $properties
        RETURN n
        """
        parameters = {"neuro_id": node.uuid, "properties": node.properties}
        self._nb.run_query(query, parameters=parameters)

    def export(self, path, label=None, **properties):
        """
        Export nodes and their relationships to a JSON file.
        Optionally filter by label and/or properties.
        """
        node = f"(n:{label})" if label else "(n)"
        conditions = ["n.`neuro.id` IS NOT NULL"]
        params = {}
        for key, value in properties.items():
            param_name = key.replace(".", "_")
            conditions.append(f"n.`{key}` = ${param_name}")
            params[param_name] = value
        where = " WHERE " + " AND ".join(conditions)

        node_query = f"""
        MATCH {node}{where}
        RETURN n.`neuro.id` as id, labels(n) as labels, properties(n) as properties
        """
        nodes = self._nb.get_data(node_query, params)

        rel_query = f"""
        MATCH {node}{where}
        WITH collect(n.`neuro.id`) as ids
        MATCH (a)-[r]->(b)
        WHERE a.`neuro.id` IN ids AND b.`neuro.id` IN ids
        RETURN a.`neuro.id` as from, b.`neuro.id` as to,
               type(r) as type, properties(r) as properties
        """
        relationships = self._nb.get_data(rel_query, params)

        data = {"nodes": nodes, "relationships": relationships}
        with open(path, "w") as f:
            json.dump(data, f, default=str)

        return data
