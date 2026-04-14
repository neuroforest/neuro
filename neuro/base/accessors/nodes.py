from neuro.core import Node
from neuro.base.accessors import Accessor
from neuro.base import nfx
from neuro.utils import exceptions


class NodeAccessor(Accessor):

    def get(self, neuro_id):
        query = """
        MATCH (ion:OntologyNode {label:"Node"})
        MATCH (on)-[:SUBCLASS_OF*0..]->(ion)
        WITH on.label as node_label

        MATCH (n)
        WHERE node_label in labels(n) AND n.`neuro.id` = $neuro_id
        RETURN properties(n) as properties, labels(n) as labels;
        """
        data = self._nb.get_data(query, {"neuro_id": neuro_id})
        if not data:
            raise ValueError(f"No node found with neuro.id: {neuro_id}")
        if len(data) > 1:
            raise ValueError(f"Multiple nodes found with neuro.id: {neuro_id}")
        return Node(labels=data[0]["labels"], properties=data[0]["properties"])

    def put(self, node):
        """
        Save a Node to the database. Merges on neuro.id, sets labels and properties.
        Validates the node against the ontology before insertion.
        :param node: Node
        """
        result = self._nb.ontology.is_valid_node(node)
        if not result:
            raise ValueError(f"Node validation failed: {result}")

        labels_str = ":".join(node.labels)
        query = f"""
        MERGE (n:{labels_str} {{`neuro.id`: $neuro_id}})
        SET n += $properties
        RETURN n
        """
        parameters = {"neuro_id": node.uuid, "properties": node.properties}
        self._nb.run_query(query, parameters=parameters)

    def import_nfx(self, path, dependency_nids=None):
        """
        Import nodes and relationships from an NFX file.
        Nodes are merged on neuro.id; relationships are merged between them.
        Validates referential integrity and jurisdiction before import.
        """
        data = nfx.read(path)

        violations = nfx.validate(data, dependency_nids)
        if violations["unresolved"] or violations["foreign"]:
            msgs = []
            for rel in violations["unresolved"]:
                msgs.append(f"  unresolved: {rel['from']} -> {rel['to']} ({rel['type']})")
            for rel in violations["foreign"]:
                msgs.append(f"  foreign: {rel['from']} -> {rel['to']} ({rel['type']})")
            raise exceptions.NfxViolation(
                f"NFX validation failed for {path}:\n" + "\n".join(msgs)
            )

        for entry in data.get("nodes", []):
            properties = entry.get("properties", {})
            properties["neuro.id"] = entry["nid"]
            node = Node(
                labels=entry["labels"],
                properties=properties,
            )
            self.put(node)

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

    def export_nfx(self, path, label=None, name="", description="", version="",
                   query=None, query_params=None, **properties):
        """
        Export nodes and their relationships to an NFX file.

        Modes (mutually exclusive, checked in order):
        - query=<cypher>: custom Cypher returning nid, labels, properties columns;
          use query_params for parameterized queries
        - default: filter by label and/or property kwargs
        """
        params = {}

        if query is not None:
            node_query = query
            params = query_params or {}
        else:
            node = f"(n:{label})" if label else "(n)"
            conditions = ["n.`neuro.id` IS NOT NULL"]
            for key, value in properties.items():
                param_name = key.replace(".", "_")
                conditions.append(f"n.`{key}` = ${param_name}")
                params[param_name] = value
            where = " WHERE " + " AND ".join(conditions)
            node_query = f"""
            MATCH {node}{where}
            RETURN n.`neuro.id` as nid, labels(n) as labels, properties(n) as properties
            """

        nodes = self._nb.get_data(node_query, params)
        ids = [n["nid"] for n in nodes]

        rel_query = """
        MATCH (a)-[r]->(b)
        WHERE a.`neuro.id` IN $ids AND b.`neuro.id` IN $ids
        RETURN a.`neuro.id` as from, b.`neuro.id` as to,
               type(r) as type, properties(r) as properties
        """
        relationships = self._nb.get_data(rel_query, {"ids": ids})

        return nfx.write(path, nodes, relationships, name=name, description=description, version=version)
