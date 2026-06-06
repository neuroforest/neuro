from neuro.core import Node
from neuro.base.accessors import Accessor
from neuro.base import nfx
from neuro.base.schema import Metarelationships, Violations
from neuro.utils import exceptions


class NodeAccessor(Accessor):

    def get(self, nid):
        query = """
        MATCH (ion:OntologyNode {label:"Node"})
        MATCH (on)-[:SUBCLASS_OF*0..]->(ion)
        WITH on.label as node_label

        MATCH (n)
        WHERE node_label in labels(n) AND n.nid = $nid
        RETURN properties(n) as properties, labels(n) as labels;
        """
        data = self._nb.get_data(query, {"nid": nid})
        if not data:
            raise ValueError(f"No node found with nid: {nid}")
        if len(data) > 1:
            raise ValueError(f"Multiple nodes found with nid: {nid}")
        return Node(labels=data[0]["labels"], properties=data[0]["properties"])

    def put(self, node):
        """
        Save a Node to the database. Merges on nid, sets labels and properties.
        Validates the node against the ontology before insertion.
        :param node: Node
        """
        self._nb.objects.put(node, identifier_key="nid")

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

    def _validate_structure(self, doc, path, dependency_nids=None):
        """Referential-integrity check on the NFX document itself (no DB writes)."""
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

    def _validate_relationship_shapes(self, doc, path):
        """Validate each relationship in `doc` against the loaded ontology.

        Source-side lineage is walked inside `Metarelationships.from_ontology`;
        target-side lineage is expanded here, so e.g. `RELATED_TO` declared on
        `Object` accepts a `Standard` target."""
        nid_labels = {entry["nid"]: entry["labels"] for entry in doc.nodes}
        violations = Violations()
        for rel in doc.relationships:
            rel_type = rel["type"]
            from_labels = nid_labels.get(rel["from"], [])
            to_labels = nid_labels.get(rel["to"], [])
            to_ancestors = self._label_ancestors(to_labels)

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

    def import_nfx(self, path, dependency_nids=None, validate=True):
        """
        Import nodes and relationships from an NFX file additively.
        Nodes are merged on nid (properties `+=`); relationships are
        merged between them. Pre-existing properties and nodes not mentioned
        in the file are left untouched. For authoritative file→DB sync, use
        `sync_nfx`.
        """
        doc = nfx.read(path)

        if validate:
            self._validate_structure(doc, path, dependency_nids)

        for entry in doc.nodes:
            properties = dict(entry.get("properties", {}))
            properties["nid"] = entry["nid"]
            node = Node(
                labels=entry["labels"],
                properties=properties,
            )
            if validate:
                self.put(node)
            else:
                self._nb.objects.put(node, identifier_key="nid", validate=False)

        if validate:
            self._validate_relationship_shapes(doc, path)

        nids = doc.node_nids

        for rel in doc.relationships:
            rel_type = rel["type"]
            match_a = "MERGE" if rel["from"] not in nids else "MATCH"
            match_b = "MERGE" if rel["to"] not in nids else "MATCH"
            query = f"""
            {match_a} (a {{nid: $from_id}})
            WITH a
            {match_b} (b {{nid: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            """
            params = {
                "from_id": rel["from"],
                "to_id": rel["to"],
                "properties": rel.get("properties", {}),
            }
            self._nb.run_query(query, params)

    def sync_nfx(self, path, dependency_nids=None, metadata_label="KnowledgeMetadata"):
        """Reconcile an NFX file into NeuroBase authoritatively.

        Anchors the file to a `KnowledgeMetadata` node (via its top-level `nid`)
        and uses `(meta)-[:DEFINES]->(node)` edges to track membership. On each
        call:

        - **Add**: nodes new in the file are created.
        - **Update**: nodes still in the file have their properties **replaced**
          (not merged) — keys absent from the file are removed.
        - **Delete**: nodes previously DEFINES-linked from this metadata that
          are absent from the file are `DETACH DELETE`d.
        - **Relationships**: edges with both endpoints in the file are
          reconciled — those not in the file are deleted, those in the file
          are upserted with property replacement. Edges with one foot outside
          the file are left alone.

        Extra labels added to retained nodes by curation are preserved.
        `metadata_label` lets the same machinery anchor different metadata
        kinds (e.g. `OntologyMetadata`).
        """
        doc = nfx.read(path)
        if not (doc.nid and doc.name):
            raise exceptions.NfxViolation(
                f"sync_nfx requires top-level nid and name "
                f"(got nid={doc.nid!r}, name={doc.name!r})"
            )

        self._validate_structure(doc, path, dependency_nids)
        self._validate_relationship_shapes(doc, path)

        meta = self._nb.metadata
        meta_props = {k: v for k, v in (
            ("name", doc.name), ("version", doc.version),
            ("description", doc.description), ("type", doc.type),
        ) if v}
        meta.upsert(
            metadata_label, doc.nid, meta_props,
            dependency_nids=[dep_nid for dep_nid, _ in doc.dependencies],
        )

        nfx_nids = list(doc.node_nids)
        meta.prune(metadata_label, doc.nid, nfx_nids)

        for entry in doc.nodes:
            properties = dict(entry.get("properties", {}))
            properties["nid"] = entry["nid"]
            node = Node(labels=entry["labels"], properties=properties)
            self._nb.objects.put(node, identifier_key="nid", replace=True)
            meta.link_defines(metadata_label, doc.nid, entry["nid"])

        self._reconcile_internal_edges(
            nfx_nids,
            [(r["from"], r["to"], r["type"]) for r in doc.relationships],
        )
        for rel in doc.relationships:
            self._nb.run_query(
                f"""
                MATCH (a {{nid: $from_id}})
                MATCH (b {{nid: $to_id}})
                MERGE (a)-[r:{rel["type"]}]->(b)
                SET r = $properties
                """,
                {
                    "from_id": rel["from"],
                    "to_id": rel["to"],
                    "properties": rel.get("properties", {}),
                },
            )

    def _reconcile_internal_edges(self, nids, keep_triples):
        """Delete every edge `(a)-[r]->(b)` where both endpoints have a
        `nid` in `nids` and the `(from, to, type)` triple is not in
        `keep_triples`. Edges with one foot outside `nids` are left alone."""
        self._nb.run_query(
            """
            MATCH (a)-[r]->(b)
            WHERE a.nid IN $nids
              AND b.nid IN $nids
            WITH r, [a.nid, b.nid, type(r)] as triple
            WHERE NOT triple IN $keep
            DELETE r
            """,
            {"nids": list(nids), "keep": [list(t) for t in keep_triples]},
        )

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
            conditions = ["n.nid IS NOT NULL"]
            for key, value in properties.items():
                param_name = key.replace(".", "_")
                conditions.append(f"n.`{key}` = ${param_name}")
                params[param_name] = value
            where = " WHERE " + " AND ".join(conditions)
            node_query = f"""
            MATCH {node}{where}
            RETURN n.nid as nid, labels(n) as labels, properties(n) as properties
            """

        nodes = self._nb.get_data(node_query, params)
        ids = [n["nid"] for n in nodes]

        rel_query = """
        MATCH (a)-[r]->(b)
        WHERE a.nid IN $ids AND b.nid IN $ids
        RETURN a.nid as from, b.nid as to,
               type(r) as type, properties(r) as properties
        """
        relationships = self._nb.get_data(rel_query, {"ids": ids})

        doc = nfx.Nfx.from_dict({
            "name": name, "description": description, "version": version,
            "nodes": nodes, "relationships": relationships,
        })
        nfx.write(path, doc)
        return doc
