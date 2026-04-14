from neuro.base.accessors import Accessor
from neuro.base.ontology import ObjectValidator


class ObjectAccessor(Accessor):

    def put(self, obj, identifier_key=None):
        """
        Save an Object to the database. Validates against the ontology before insertion.

        :param obj: Object with .labels and .properties
        :param identifier_key: property key used as MERGE key (e.g. "neuro.id").
            If provided, MERGE on that property; otherwise CREATE.
        """
        validator = ObjectValidator(self._nb, obj)
        violations = validator.get_violations()
        if violations:
            raise ValueError(f"Object validation failed: {violations}")

        labels_str = ":".join(obj.labels)

        if identifier_key:
            param_name = identifier_key.replace(".", "_")
            query = f"""
            MERGE (n:{labels_str} {{`{identifier_key}`: ${param_name}}})
            SET n += $properties
            RETURN n
            """
            parameters = {
                param_name: obj.properties[identifier_key],
                "properties": obj.properties,
            }
        else:
            query = f"""
            CREATE (n:{labels_str})
            SET n += $properties
            RETURN n
            """
            parameters = {"properties": obj.properties}

        self._nb.run_query(query, parameters=parameters)
