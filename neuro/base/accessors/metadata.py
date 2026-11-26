from neuro.base.accessors import Accessor


class MetadataAccessor(Accessor):
    """Operations on `*Metadata` anchor nodes and their membership edges.

    A metadata node (`OntologyMetadata`, `KnowledgeMetadata`, ...) anchors an
    NFX file in the graph: `(:Metadata)-[:DEFINES]->(node)` tracks which nodes
    belong to it, and `(:Metadata)-[:DEPENDS_ON]->(:Metadata)` records cross-file
    dependencies. This accessor centralizes the Cypher for those edges so the
    ontology- and knowledge-import paths share one implementation.
    """

    def upsert(self, label, nid, properties=None, dependency_nids=()):
        """MERGE a metadata anchor and re-link its `DEPENDS_ON` edges.

        Existing DEPENDS_ON edges from this anchor are dropped and replaced by
        edges to the listed dependency nids - so the anchor's dependency set
        always matches the caller's input."""
        properties = properties or {}
        self._nb.run_query(
            f"MERGE (m:{label} {{nid: $nid}}) SET m += $props",
            {"nid": nid, "props": properties},
        )
        self._nb.run_query(
            f"""
            MATCH (m:{label} {{nid: $nid}})-[r:DEPENDS_ON]->()
            DELETE r
            """,
            {"nid": nid},
        )
        for dep_nid in dependency_nids:
            self._nb.run_query(
                f"""
                MATCH (m:{label} {{nid: $nid}})
                MATCH (d:OntologyMetadata|KnowledgeMetadata {{nid: $dep_nid}})
                MERGE (m)-[:DEPENDS_ON]->(d)
                """,
                {"nid": nid, "dep_nid": dep_nid},
            )

    def set_namespace(self, label, nid, namespace):
        """Record the token of the tree a module was imported from.

        A module's name is unique inside its tree only, so the anchor carries
        the tree's token beside it: "" for the root namespace, and no property
        at all (`namespace` None) for a module that came from a legacy root."""
        self._nb.run_query(
            f"MATCH (m:{label} {{nid: $nid}}) SET m.namespace = $namespace",
            {"nid": nid, "namespace": namespace},
        )

    def link_defines(self, label, meta_nid, node_nid, node_label=None):
        """MERGE `(meta)-[:DEFINES]->(node)` by nid. `node_label`, when known,
        scopes the node lookup - an unlabelled one scans the base."""
        node = f"(n:`{node_label.replace('`', '``')}` {{nid: $node_nid}})" if node_label else "(n {nid: $node_nid})"
        self._nb.run_query(
            f"""
            MATCH (m:{label} {{nid: $meta_nid}})
            MATCH {node}
            MERGE (m)-[:DEFINES]->(n)
            """,
            {"meta_nid": meta_nid, "node_nid": node_nid},
        )
