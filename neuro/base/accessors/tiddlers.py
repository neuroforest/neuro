from neuro.base.accessors import Accessor


class TiddlerAccessor(Accessor):

    def all_fields(self):
        query = """
        MATCH (t:Tiddler)
        RETURN t {
            .*,
            created: toString(t.created),
            modified: toString(t.modified)
        } as properties;
        """
        try:
            self._nb.driver.verify_connectivity()
            result = self._nb.get_data(query)
            fields_list = [next(iter(record.values())) for record in result]
        except Exception as e:
            print(f"Error connecting to Neo4j: {e}")
            return None

        return fields_list
