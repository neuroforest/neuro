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
