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

    def put(self, o):
        """
        Save an object to the database.
        :param o: dict that includes keys 'title' and 'neuro.id'
        """
        if "title" not in o:
            raise ValueError("Object must have a 'title' field")
        if "neuro.id" not in o:
            raise ValueError(f"Object must have a 'neuro.id' field {o}")

        query = """
        MERGE (o:Object {title: $title, `neuro.id`: $neuro_id})
        SET o += $fields
        RETURN o
        """
        parameters = {"title": o["title"], "neuro_id": o["neuro.id"], "fields": o}
        self._nb.run_query(query, parameters=parameters)
