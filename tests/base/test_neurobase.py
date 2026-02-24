"""
Integration tests for NeuroBase database availability.
"""

import pytest

from neuro.core import Node


@pytest.mark.integration
class TestNeuroBase:
    def test_connectivity(self, nb):
        nb.driver.verify_connectivity()

    def test_count_nodes(self, nb):
        count = nb.count()
        assert isinstance(count, int)


@pytest.mark.integration
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

        original = nfx.read(get_path("resources") / "metaontology.nfx")
        export_path = tmp_path / "metaontology_export.nfx"
        nb_meta.metaontology.export_nfx(export_path)
        exported = nfx.read(export_path)

        node_diff = deepdiff.DeepDiff(original["nodes"], exported["nodes"], ignore_order=True)
        assert node_diff == {}, f"Nodes mismatch:\n{node_diff}"

        rel_diff = deepdiff.DeepDiff(original["relationships"], exported["relationships"], ignore_order=True)
        assert rel_diff == {}, f"Relationships mismatch:\n{rel_diff}"
