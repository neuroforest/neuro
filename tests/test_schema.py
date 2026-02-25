"""
Unit tests for neuro.base.schema — property value validation.
"""

import neo4j.time

from neuro.base.schema import Metaproperty


def _make_metaproperty(property_type, deep_node="OntologyNode"):
    return Metaproperty({
        "property": "test",
        "node": "Test",
        "node_object": None,
        "property_object": None,
        "property_type": property_type,
        "relationship_type": "HAS_PROPERTY",
        "deep_node": deep_node,
    })


class TestCheckUuid:
    mp = _make_metaproperty("Uuid")

    def test_valid(self):
        assert self.mp.check("550e8400-e29b-41d4-a716-446655440000") is None

    def test_wrong_version(self):
        # UUID v1
        assert self.mp.check("550e8400-e29b-11d4-a716-446655440000") is not None

    def test_not_a_uuid(self):
        assert self.mp.check("not-a-uuid") is not None

    def test_not_a_string(self):
        assert self.mp.check(123) is not None


class TestCheckString:
    mp = _make_metaproperty("String")

    def test_valid(self):
        assert self.mp.check("hello") is None

    def test_integer(self):
        assert self.mp.check(42) is not None

    def test_none(self):
        assert self.mp.check(None) is not None


class TestCheckLabel:
    def test_node_valid(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert mp.check("Tiddler") is None

    def test_node_lowercase(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert mp.check("tiddler") is not None

    def test_node_with_hyphen(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert mp.check("bad-label") is not None

    def test_relationship_valid(self):
        mp = _make_metaproperty("Label", "OntologyRelationship")
        assert mp.check("PARENT_OF") is None

    def test_relationship_lowercase(self):
        mp = _make_metaproperty("Label", "OntologyRelationship")
        assert mp.check("parent_of") is not None

    def test_property_valid(self):
        mp = _make_metaproperty("Label", "OntologyProperty")
        assert mp.check("neuro.id") is None

    def test_property_uppercase(self):
        mp = _make_metaproperty("Label", "OntologyProperty")
        assert mp.check("Neuro") is not None


class TestCheckDateTime:
    mp = _make_metaproperty("DateTime")

    def test_valid(self):
        dt = neo4j.time.DateTime(2025, 1, 1, 0, 0, 0)
        assert self.mp.check(dt) is None

    def test_string(self):
        assert self.mp.check("2025-01-01") is not None


class TestCheckUnknownType:
    mp = _make_metaproperty("BogusType")

    def test_returns_reason(self):
        result = self.mp.check("anything")
        assert result is not None
        assert "no check" in result
