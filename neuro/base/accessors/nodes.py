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
        - **Foreign references**: a node whose nid is in `dependency_nids` is
          owned by a dependency and only re-declared here to anchor this file's
          own edges; it is left entirely untouched (not property-replaced, not
          DEFINES-linked, not pruned), so its owner's properties survive — the
          same treatment ontology import gives a cross-ontology reference.
        - **Relationships**: edges with both endpoints in the file are
          reconciled *within the edge types the file declares* — an edge of a
          managed type not in the file is deleted, those in the file are
          upserted with property replacement. Edges of a type the file never
          declares (and edges with one foot outside the file) are left alone,
          so a file that declares stub nodes only to hang its own edge type off
          them can't reap the foreign structural edges among those nodes.

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

        # A node whose nid belongs to a dependency is a *foreign reference* — the
        # file re-declares it only so its own edges have a resolvable endpoint
        # (and so the file validates standalone). Its properties are the owner's,
        # not this file's: `replace=True` would strip whatever the file omits
        # (e.g. the `color` an OntologyNode class carries), and `link_defines`
        # would make this metadata co-own it and later prune it. So ensure it
        # exists but touch nothing else — exactly how ontology import treats a
        # cross-ontology reference. `_reconcile_internal_edges` still sees it via
        # `nfx_nids`, so edges landing on it are managed as before.
        foreign = set(dependency_nids or ())
        for entry in doc.nodes:
            if entry["nid"] in foreign:
                continue
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

    def _reconcile_internal_edges(self, nids, keep_triples, sources=None):
        """Delete every edge `(a)-[r]->(b)` where both endpoints have a `nid`
        in `nids`, the edge's **type is one the file declares**, and the
        `(from, to, type)` triple is not in `keep_triples`. Edges with one foot
        outside `nids` are left alone.

        `sources`, when given, additionally restricts the tail: only edges
        leaving a node the file itself *declares* are candidates. Without it a
        file that merely references both endpoints of a foreign edge reaps it
        — e.g. `sequencing` declaring `ShovillRun SUBCLASS_OF PipelineRun` and
        `Assembly SUBCLASS_OF Node` puts both `PipelineRun` and `Node` in scope
        and silently deletes `provenance`\'s own `PipelineRun SUBCLASS_OF Node`.
        A file owns the edges leaving its own nodes, not every edge between
        nodes it happens to name.

        The type gate matters when a file declares a node purely to be a
        relationship *target* (e.g. metrics knowledge declaring stub
        `OntologyNode`s for the classes its `APPLIES_TO` edges point at). Such
        stubs make the file's node set span a slice of the pre-existing graph —
        and a blanket "delete any internal edge not in the file" would then
        reap foreign-typed structural edges the file never owned (the
        `SUBCLASS_OF` edges among those classes). A file authoritatively owns
        only the edge *types* it declares, so reconciliation is scoped to them;
        a type absent from the file is left entirely untouched."""
        managed_types = sorted({t for _, _, t in keep_triples})
        rows = self._nb.get_data(
            """
            MATCH (a)-[r]->(b)
            WHERE a.nid IN $nids
              AND b.nid IN $nids
              AND type(r) IN $managed
              AND ($sources IS NULL OR a.nid IN $sources)
            WITH r, [a.nid, b.nid, type(r)] as triple
            WHERE NOT triple IN $keep
            WITH collect(r) as pruned
            FOREACH (r IN pruned | DELETE r)
            RETURN size(pruned) as pruned
            """,
            {"nids": list(nids), "managed": managed_types,
             "keep": [list(t) for t in keep_triples],
             "sources": None if sources is None else list(sources)},
        )
        return rows[0]["pruned"] if rows else 0

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
