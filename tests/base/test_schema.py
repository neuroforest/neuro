"""
Unit tests for neuro.base.schema — property value validation.
"""

import pytest
import neo4j.time

from neuro.base.schema import Metaproperty, Metarelationship

pytestmark = pytest.mark.unit


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
        assert self.mp.check("550e8400-e29b-41d4-a716-446655440000")

    def test_wrong_version(self):
        # UUID v1
        assert not self.mp.check("550e8400-e29b-11d4-a716-446655440000")

    def test_not_a_uuid(self):
        assert not self.mp.check("not-a-uuid")

    def test_not_a_string(self):
        assert not self.mp.check(123)


class TestCheckString:
    mp = _make_metaproperty("String")

    def test_valid(self):
        assert self.mp.check("hello")

    def test_integer(self):
        assert not self.mp.check(42)

    def test_none(self):
        assert not self.mp.check(None)


class TestCheckLabel:
    def test_node_valid(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert mp.check("Tiddler")

    def test_node_lowercase(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert not mp.check("tiddler")

    def test_node_with_hyphen(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert not mp.check("bad-label")

    def test_relationship_valid(self):
        mp = _make_metaproperty("Label", "OntologyRelationship")
        assert mp.check("PARENT_OF")

    def test_relationship_lowercase(self):
        mp = _make_metaproperty("Label", "OntologyRelationship")
        assert not mp.check("parent_of")

    def test_property_valid(self):
        mp = _make_metaproperty("Label", "OntologyProperty")
        assert mp.check("neuro.id")

    def test_property_uppercase(self):
        mp = _make_metaproperty("Label", "OntologyProperty")
        assert not mp.check("Neuro")


class TestCheckDateTime:
    mp = _make_metaproperty("DateTime")

    def test_valid(self):
        dt = neo4j.time.DateTime(2025, 1, 1, 0, 0, 0)
        assert self.mp.check(dt)

    def test_string(self):
        assert not self.mp.check("2025-01-01")


class TestCheckUnknownType:
    mp = _make_metaproperty("BogusType")

    def test_returns_false(self):
        assert not self.mp.check("anything")


class TestMetarelationship:
    mr = Metarelationship({"relationship": "PARENT_OF", "source": "Taxon", "target": "Taxon",
                           "relationship_type": "HAS_RELATIONSHIP"})

    def test_repr(self):
        assert repr(self.mr) == "<Metarelationship (Taxon)-[:PARENT_OF]->(Taxon)>"

    def test_direction_source(self):
        assert self.mr.direction("Taxon") == "outgoing"

    def test_direction_unrelated(self):
        assert self.mr.direction("Gene") is None

    def test_direction_asymmetric(self):
        mr = Metarelationship({"relationship": "HAS_GENE", "source": "Genome", "target": "Gene",
                               "relationship_type": "HAS_RELATIONSHIP"})
        assert mr.direction("Genome") == "outgoing"
        assert mr.direction("Gene") == "incoming"

    def test_is_required(self):
        mr = Metarelationship({"relationship": "HAS_GENE", "source": "Genome", "target": "Gene",
                               "relationship_type": "REQUIRE_RELATIONSHIP"})
        assert mr.is_required()
        assert not self.mr.is_required()
