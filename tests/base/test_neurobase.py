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
        """Getting a nonexistent neuro.id raises ValueError."""
        with pytest.raises(ValueError, match="No node found"):
            nb.nodes.get("nonexistent-uuid-000")

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
