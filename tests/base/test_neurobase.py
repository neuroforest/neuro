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
    def test_get_returns_node(self, nb):
        """Put a node, then get it back by neuro.id."""
        node = Node(labels=["Tiddler"], properties={"title": "test_get_node"})
        nb.nodes.put(node)
        result = nb.nodes.get(node.uuid)
        assert isinstance(result, Node)
        assert result.uuid == node.uuid
        assert "Tiddler" in result.labels
        assert result.properties["title"] == "test_get_node"

    def test_get_not_found(self, nb):
        """Getting a nonexistent neuro.id raises ValueError."""
        with pytest.raises(ValueError, match="No node found"):
            nb.nodes.get("nonexistent-uuid-000")

    def test_get_preserves_labels(self, nb):
        """A node with multiple labels retains all of them."""
        node = Node(labels=["Tiddler", "Species"], properties={"title": "test_multi_label"})
        nb.nodes.put(node)
        result = nb.nodes.get(node.uuid)
        assert "Tiddler" in result.labels
        assert "Species" in result.labels

    def test_get_preserves_properties(self, nb):
        """Properties survive the put/get round-trip."""
        node = Node(
            labels=["Tiddler"],
            properties={"title": "test_props", "neuro.role": "taxon.species", "custom_field": "value"}
        )
        nb.nodes.put(node)
        result = nb.nodes.get(node.uuid)
        assert result.properties["neuro.role"] == "taxon.species"
        assert result.properties["custom_field"] == "value"
