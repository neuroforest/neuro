from neuro.core import Node
from neuro.base.accessors import Accessor
from neuro.base import nfx
from neuro.base.schema import Metarelationships, Violations
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
        self._nb.objects.put(node, identifier_key="neuro.id")

    def _label_ancestors(self, labels):
        """Expand a list of node labels to the union of themselves and all
        SUBCLASS_OF ancestors. Used to match a metarelationship's target
        against an instance node whose declared labels don't include lineage."""
        if not labels:
            return set()
        query = """
        UNWIND $labels as lbl
        MATCH (n:OntologyNode {label: lbl})
        MATCH (n)-[:SUBCLASS_OF*0..]->(a:OntologyNode)
        RETURN DISTINCT a.label as label
        """
        data = self._nb.get_data(query, {"labels": list(labels)})
        return {r["label"] for r in data}

    def import_nfx(self, path, dependency_nids=None, validate=True):
        """
        Import nodes and relationships from an NFX file.
        Nodes are merged on neuro.id; relationships are merged between them.
        Validates referential integrity and jurisdiction before import.
        """
        doc = nfx.read(path)

        if validate:
            violations = nfx.validate(doc, dependency_nids)
            if violations["unresolved"] or violations["foreign"]:
                msgs = []
                for rel in violations["unresolved"]:
                    msgs.append(f"  unresolved: {rel['from']} -> {rel['to']} ({rel['type']})")
                for rel in violations["foreign"]:
                    msgs.append(f"  foreign: {rel['from']} -> {rel['to']} ({rel['type']})")
                raise exceptions.NfxViolation(
                    f"NFX validation failed for {path}:\n" + "\n".join(msgs)
                )

        for entry in doc.nodes:
            properties = dict(entry.get("properties", {}))
            properties["neuro.id"] = entry["nid"]
            node = Node(
                labels=entry["labels"],
                properties=properties,
            )
            if validate:
                self.put(node)
            else:
                self._nb.objects.put(node, identifier_key="neuro.id", validate=False)

        if validate:
            # Build label lookup from imported nodes for relationship validation
            nid_labels = {entry["nid"]: entry["labels"] for entry in doc.nodes}

            violations = Violations()
            for rel in doc.relationships:
                rel_type = rel["type"]
                from_labels = nid_labels.get(rel["from"], [])
                to_labels = nid_labels.get(rel["to"], [])
                to_ancestors = self._label_ancestors(to_labels)

                # Validate against the source node's metarelationships.
                # `Metarelationships.from_ontology` already follows SUBCLASS_OF
                # on the source side; we expand `to_labels` here to mirror that
                # on the target side, so e.g. `RELATED_TO` declared on `Object`
                # accepts a `Standard` target.
                candidates = []
                for label in from_labels:
                    mrs = Metarelationships.from_ontology(self._nb, label)
                    candidates.extend(
                        m for k, m in mrs.items()
                        if m.label == rel_type and k.endswith(":outgoing") and m.target
                    )
                    if candidates:
                        break

                if not candidates:
                    violations.undefined_relationships.append(
                        (rel_type, "outgoing", to_labels)
                    )
                elif not any(m.target in to_ancestors for m in candidates):
                    expected = sorted({m.target for m in candidates})
                    violations.invalid_relationships.append(
                        (rel_type, "outgoing", to_labels,
                         expected[0] if len(expected) == 1 else expected)
                    )

            if violations:
                raise exceptions.NfxViolation(
                    f"Relationship validation failed for {path}:\n{violations}"
                )

        nids = doc.node_nids

        for rel in doc.relationships:
            rel_type = rel["type"]
            match_a = "MERGE" if rel["from"] not in nids else "MATCH"
            match_b = "MERGE" if rel["to"] not in nids else "MATCH"
            query = f"""
            {match_a} (a {{`neuro.id`: $from_id}})
            WITH a
            {match_b} (b {{`neuro.id`: $to_id}})
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

        doc = nfx.Nfx.from_dict({
            "name": name, "description": description, "version": version,
            "nodes": nodes, "relationships": relationships,
        })
        nfx.write(path, doc)
        return doc
