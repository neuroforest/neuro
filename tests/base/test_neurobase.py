"""
Integration tests for NeuroBase database availability.
"""

import pytest


class TestNeuroBase:
    def test_connectivity(self, nb):
        nb.driver.verify_connectivity()

    def test_count_nodes(self, nb):
        count = nb.count()
        assert isinstance(count, int)


class TestOntology:
    def test_clear_preserves_data_nodes(self, nb_meta):
        """nb.ontology.clear() must not delete non-ontology nodes."""
        nb_meta.run_query("""
            MATCH (o:OntologyNode {label: "OntologyNode"})
            CREATE (d:DataNode {name: "test-data-clear", value: "hello"})
            CREATE (d)-[:LINKED_TO]->(o)
        """)

        assert nb_meta.count("DataNode") == 1
        nb_meta.ontology.clear(confirm=True)
        assert nb_meta.count("OntologyNode") == 0
        assert nb_meta.count("DataNode") == 1
        r = nb_meta.get_data("MATCH (d:DataNode {name: 'test-data-clear'}) RETURN d.value as v")
        assert r[0]["v"] == "hello"


class TestNodeAccessor:
    def test_get_not_found(self, nb):
        """Getting a nonexistent nid raises ValueError."""
        with pytest.raises(ValueError, match="No node found"):
            nb.nodes.get("nonexistent-uuid-000")

    def test_reconcile_internal_edges_is_type_scoped(self, nb):
        """Reconciliation only touches the edge types the file declares.

        Regression: a knowledge file that declares stub nodes purely to be
        `APPLIES_TO` targets (e.g. metrics pointing at a class + its subclasses)
        must not reap the foreign `SUBCLASS_OF` edges among those co-declared
        nodes — a blanket "delete any internal edge not in the file" did, which
        silently broke the ontology's subclass tree on every knowledge import.
        """
        nb.run_query(
            """
            CREATE (parent {nid: 'rc-parent'})
            CREATE (child  {nid: 'rc-child'})
            CREATE (metric {nid: 'rc-metric'})
            CREATE (child)-[:SUBCLASS_OF]->(parent)
            CREATE (metric)-[:APPLIES_TO]->(parent)
            CREATE (metric)-[:APPLIES_TO]->(child)
            """
        )
        nids = ["rc-parent", "rc-child", "rc-metric"]

        def edges():
            rows = nb.get_data(
                "MATCH (a)-[r]->(b) WHERE a.nid IN $nids AND b.nid IN $nids "
                "RETURN a.nid AS f, b.nid AS t, type(r) AS ty",
                {"nids": nids},
            )
            return {(r["f"], r["t"], r["ty"]) for r in rows}

        # The file declares only its APPLIES_TO edges (never SUBCLASS_OF).
        nb.nodes._reconcile_internal_edges(
            nids,
            [("rc-metric", "rc-parent", "APPLIES_TO"),
             ("rc-metric", "rc-child", "APPLIES_TO")],
        )
        assert ("rc-child", "rc-parent", "SUBCLASS_OF") in edges(), \
            "foreign SUBCLASS_OF edge must survive reconciliation"
        assert ("rc-metric", "rc-child", "APPLIES_TO") in edges()

        # Dropping a managed (APPLIES_TO) edge from the file still prunes it,
        # while the untouched foreign type stays put.
        nb.nodes._reconcile_internal_edges(
            nids,
            [("rc-metric", "rc-parent", "APPLIES_TO")],
        )
        assert edges() == {
            ("rc-child", "rc-parent", "SUBCLASS_OF"),
            ("rc-metric", "rc-parent", "APPLIES_TO"),
        }

    def test_nfx_integrity(self, nb_meta, tmp_path):
        """Export metaontology NFX and verify node/relationship integrity."""
        import deepdiff
        from neuro.base import nfx
        from neuro.utils.internal_utils import get_path

        original = nfx.read(get_path("assets") / "ontology" / "metaontology.nfx")
        export_path = tmp_path / "metaontology_export.nfx"
        nb_meta.metaontology.export_nfx(export_path)
        exported = nfx.read(export_path)

        node_diff = deepdiff.DeepDiff(list(original.nodes), list(exported.nodes), ignore_order=True)
        assert node_diff == {}, f"Nodes mismatch:\n{node_diff}"

        rel_diff = deepdiff.DeepDiff(list(original.relationships), list(exported.relationships), ignore_order=True)
        assert rel_diff == {}, f"Relationships mismatch:\n{rel_diff}"
