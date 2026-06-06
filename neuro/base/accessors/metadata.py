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
        edges to the listed dependency nids — so the anchor's dependency set
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
                MATCH (d {{nid: $dep_nid}})
                MERGE (m)-[:DEPENDS_ON]->(d)
                """,
                {"nid": nid, "dep_nid": dep_nid},
            )

    def link_defines(self, label, meta_nid, node_nid):
        """MERGE `(meta)-[:DEFINES]->(node)` by nid."""
        self._nb.run_query(
            f"""
            MATCH (m:{label} {{nid: $meta_nid}})
            MATCH (n {{nid: $node_nid}})
            MERGE (m)-[:DEFINES]->(n)
            """,
            {"meta_nid": meta_nid, "node_nid": node_nid},
        )

    def prune(self, label, meta_nid, keep_nids):
        """`DETACH DELETE` every node DEFINES-linked from this anchor whose
        nid is not in `keep_nids`. Used to drop nodes that were imported
        previously but are absent from the current NFX."""
        self._nb.run_query(
            f"""
            MATCH (m:{label} {{nid: $meta_nid}})-[:DEFINES]->(n)
            WHERE NOT n.nid IN $nids
            DETACH DELETE n
            """,
            {"meta_nid": meta_nid, "nids": list(keep_nids)},
        )
