import os
import logging

import neo4j

from neuro.base.accessors.nodes import NodeAccessor
from neuro.base.accessors.tiddlers import TiddlerAccessor


class NeuroBase:
    """
    Simple, reusable Neo4j client wrapper.
    """
    def __init__(self, neo4j_uri=None, neo4j_user=None, neo4j_password=None, **kwargs):
        uri = neo4j_uri or os.getenv("NEO4J_URI")
        user = neo4j_user or os.getenv("NEO4J_USER")
        password = neo4j_password or os.getenv("NEO4J_PASSWORD")
        try:
            self.driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
        except neo4j.exceptions.ConfigurationError:
            logging.error(f"Incorrect Neo4j parameters: {uri}")
            return

        # accessors
        self.nodes = NodeAccessor(self)
        self.tiddlers = TiddlerAccessor(self)

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
        logging.debug(f"NeuroBase.get_data query: {query}")
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            records = [record.data() for record in result]
            return records

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """
        Close the driver.
        """
        if self.driver:
            self.driver.close()
