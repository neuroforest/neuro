from neuro.core import Node
from neuro.base.accessors import Accessor
from neuro.base.ontology import ObjectValidator


class ObjectAccessor(Accessor):

    def illuminate(self, query, query_params=None, dry_run=False):
        """
        Stamp `nid` on nodes returned by `query`.
        Without an id a node is invisible to ontology validation; illuminating
        brings it into the validator's view.

        :param query: Cypher returning an `eid` column (elementId of nodes to stamp).
            Caller owns the filter — typically ``WHERE n.nid IS NULL``.
        :param query_params: optional dict of parameters for `query`.
        :param dry_run: if True, return elementIds that would be stamped without writing.
        :return: count of stamped nodes (or list of elementIds when dry_run).
        """
        rows = self._nb.get_data(query, query_params or {})
        eids = [r["eid"] for r in rows]
        if dry_run:
            return eids
        stamp_query = """
        MATCH (n) WHERE elementId(n) = $eid
        SET n.nid = $new_id
        """
        for eid in eids:
            self._nb.run_query(stamp_query, {
                "eid": eid,
                "new_id": Node.generate_nid(),
            })
        return len(eids)

    def put(self, obj, identifier_key=None, validate=True, replace=False):
        """
        Save an Object to the database. Validates against the ontology before insertion.

        :param obj: Object with .labels and .properties
        :param identifier_key: property key used as MERGE key (e.g. "nid").
            If provided, MERGE on that property; otherwise CREATE.
        :param validate: if False, skip ontology validation.
        :param replace: if True, replace the node's full property map (`SET n = $properties`)
            instead of merging it (`SET n += $properties`). Properties absent
            from `obj.properties` are removed from the existing node. Requires
            `identifier_key`. Use for authoritative file→DB sync; default
            `False` preserves the original additive behavior.
        """
        if validate:
            validator = ObjectValidator(self._nb, obj)
            violations = validator.get_violations()
            if violations:
                raise ValueError(f"Object validation failed: {violations}")

        labels_str = ":".join(obj.labels)
        set_op = "=" if replace else "+="

        if identifier_key:
            param_name = identifier_key.replace(".", "_")
            query = f"""
            MERGE (n:{labels_str} {{`{identifier_key}`: ${param_name}}})
            SET n {set_op} $properties
            RETURN n
            """
            parameters = {
                param_name: obj.properties[identifier_key],
                "properties": obj.properties,
            }
        elif replace:
            raise ValueError("replace=True requires identifier_key")
        else:
            query = f"""
            CREATE (n:{labels_str})
            SET n += $properties
            RETURN n
            """
            parameters = {"properties": obj.properties}

        self._nb.run_query(query, parameters=parameters)
