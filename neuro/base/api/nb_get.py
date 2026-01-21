from neuro.core import Node
from neuro.base.api import NeuroBase


def all_tiddlers(**kwargs):
    """
    Run a Cypher query and return the tiddlers as a list of dicts.
    """
    nb = NeuroBase(**kwargs)
    try:
        nb.driver.verify_connectivity()
        query = """
        MATCH (t:Tiddler)
        RETURN t { 
            .*, 
            created: toString(t.created),
            modified: toString(t.modified) 
        } as properties;
        """
        result = nb.get_data(query)
        tiddlers = [next(iter(record.values())) for record in result]
    except Exception as e:
        print(f"Error connecting to Neo4j: {e}")
        return None
    finally:
        nb.close()

    return tiddlers


def node_by_uuid(neuro_id):
    query = f"""
    MATCH (ion:OntologyNode {{label:"Node"}})
    MATCH (on)-[:SUBCLASS_OF*0..]->(ion)
    WITH on.label as node_label
    
    MATCH (n)
    WHERE node_label in labels(n) AND n.`neuro.id` = "{neuro_id}"
    RETURN n as properties, labels(n) as labels, n.`neuro.id` as uuid;
    """
    nb = NeuroBase()
    data = nb.get_data(query)
    if not data:
        raise ValueError(f"No node found with neuro.id: {neuro_id}")
    if len(data) > 1:
        raise ValueError(f"Multiple nodes found with neuro.id: {neuro_id}")
    else:
        node = Node(uuid=data[0]["uuid"], labels=data[0]["labels"], properties=data[0]["properties"])
        return node
