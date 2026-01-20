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
