import os
import logging

import neo4j


class NeuroBase:
    """
    Simple, reusable Neo4j client wrapper.
    """
    def __init__(self, neo4j_uri=None, neo4j_user=None, neo4j_password=None, **kwargs):
        uri = neo4j_uri or os.getenv("NEO4J_URI")
        print(uri)
        user = neo4j_user or os.getenv("NEO4J_USER")
        password = neo4j_password or os.getenv("NEO4J_PASSWORD")
        try:
            self.driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
        except neo4j.exceptions.ConfigurationError:
            logging.error(f"Incorrect Neo4j parameters: {uri}")
            return

    def run_query(self, query, parameters=None):
        """
        Run a Cypher query and return the result.
        """
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return result

    def get_data(self, query, parameters=None):
        """
        Run a Cypher query and return the data as a list of records.
        """
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            records = [record.data() for record in result]
            return records

    def save_object(self, o):
        """
        Save an object to the database.
        :param o: dict that includes keys 'title' and 'neuro.id'
        :return:
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
        self.run_query(query, parameters=parameters)

    def clear(self, confirm=False):
        if not confirm:
            raise ValueError("Refusing to clear database without confirm=True")

        query = """
            MATCH (o)
            DETACH DELETE o;
        """
        self.run_query(query)

    def count_nodes(self):
        """
        Count the total number of nodes in the database.
        """
        query = "MATCH (n) RETURN count(n) AS count"
        result = self.get_data(query)
        return result[0]["count"]

    def close(self):
        """
        Close the driver.
        """
        if self.driver:
            self.driver.close()