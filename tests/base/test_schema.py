"""
Unit tests for neuro.base.schema - Metaproperty/Metarelationship behavior.

Metaontology core validators (String, Uuid, Label, OntologyProperty) are
hardcoded in `Metaproperty.check` and tested here. Non-core validators
(DateTime, Title, …) live with their plugin under `<plugin>/test_validators.py`.
"""

import pytest

from neuro.base.schema import (
    Metaproperties,
    MetapropertiesUnion,
    Metaproperty,
    Metarelationship,
)

pytestmark = pytest.mark.unit


def _make_metaproperty(property_type, deep_node="OntologyNode"):
    return Metaproperty({
        "property": "test",
        "node": "Test",
        "node_object": None,
        "property_object": None,
        "property_type": property_type,
        "relationship_type": "HAS_PROPERTY",
        "relationship_lineage": ["HAS_PROPERTY"],
        "deep_node": deep_node,
        "distance": 0,
    })


class TestCheckUnknownType:
    """Fail-closed for unregistered property types."""
    mp = _make_metaproperty("BogusType")

    def test_returns_false(self):
        assert not self.mp.validate("anything")


class TestUuid:
    mp = _make_metaproperty("Uuid")

    def test_valid(self):
        assert self.mp.validate("550e8400-e29b-41d4-a716-446655440000")

    def test_wrong_version(self):
        assert not self.mp.validate("550e8400-e29b-11d4-a716-446655440000")

    def test_not_a_uuid(self):
        assert not self.mp.validate("not-a-uuid")

    def test_not_a_string(self):
        assert not self.mp.validate(123)


class TestString:
    mp = _make_metaproperty("String")

    def test_valid(self):
        assert self.mp.validate("hello")

    def test_integer(self):
        assert not self.mp.validate(42)

    def test_none(self):
        assert not self.mp.validate(None)


class TestColor:
    mp = _make_metaproperty("Color")

    def test_valid(self):
        assert self.mp.validate("#ff0000")

    def test_uppercase(self):
        assert not self.mp.validate("#FF0000")

    def test_shorthand(self):
        assert not self.mp.validate("#f00")

    def test_named(self):
        assert not self.mp.validate("red")

    def test_alpha(self):
        assert not self.mp.validate("#ff000000")

    def test_not_a_string(self):
        assert not self.mp.validate(0xff0000)


class TestLabel:
    def test_node_valid(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert mp.validate("Tiddler")

    def test_node_lowercase(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert not mp.validate("tiddler")

    def test_node_with_hyphen(self):
        mp = _make_metaproperty("Label", "OntologyNode")
        assert not mp.validate("bad-label")

    def test_relationship_valid(self):
        mp = _make_metaproperty("Label", "OntologyRelationship")
        assert mp.validate("PARENT_OF")

    def test_relationship_lowercase(self):
        mp = _make_metaproperty("Label", "OntologyRelationship")
        assert not mp.validate("parent_of")

    def test_property_valid(self):
        mp = _make_metaproperty("Label", "OntologyProperty")
        assert mp.validate("nid")

    def test_property_uppercase(self):
        mp = _make_metaproperty("Label", "OntologyProperty")
        assert not mp.validate("Neuro")


class TestOntologyProperty:
    """OntologyProperty is abstract - values of this declared type always fail."""
    mp = _make_metaproperty("OntologyProperty")

    def test_always_invalid(self):
        assert not self.mp.validate("anything")
        assert not self.mp.validate(42)


class TestUnvalidatedFallback:
    """Unregistered types: default falls back to String (warn on str, fail otherwise); strict always fails."""

    def _metaprops(self, property_type):
        mps = Metaproperties("Test")
        mps["test"] = _make_metaproperty(property_type)
        return mps

    def test_string_value_warns(self):
        mps = self._metaprops("BogusType")
        v = mps.validate_properties({"test": "hello"})
        assert not v
        assert v.warnings
        assert "BogusType" in v.warnings[0]
        assert "String" in v.warnings[0]

    def test_non_string_value_fails(self):
        mps = self._metaprops("BogusType")
        v = mps.validate_properties({"test": 42})
        assert v
        assert v.invalid_properties
        reason = v.invalid_properties[0][1]
        assert "BogusType" in reason and "not String" in reason

    def test_strict_string_value_fails(self):
        mps = self._metaprops("BogusType")
        v = mps.validate_properties({"test": "hello"}, strict=True)
        assert v
        assert not v.warnings
        assert v.invalid_properties[0][1] == "unvalidated data type: BogusType"

    def test_strict_non_string_value_fails(self):
        mps = self._metaprops("BogusType")
        v = mps.validate_properties({"test": 42}, strict=True)
        assert v
        assert v.invalid_properties[0][1] == "unvalidated data type: BogusType"


class TestMetarelationship:
    mr = Metarelationship({"relationship": "PARENT_OF", "source": "Taxon", "target": "Taxon",
                           "relationship_type": "HAS_RELATIONSHIP",
                           "target_link_type": "HAS_TARGET"})

    def test_repr(self):
        assert repr(self.mr) == "<Metarelationship (Taxon)-[:PARENT_OF]->(Taxon)>"

    def test_direction_source(self):
        assert self.mr.direction("Taxon") == "outgoing"

    def test_direction_unrelated(self):
        assert self.mr.direction("Gene") is None

    def test_direction_asymmetric(self):
        mr = Metarelationship({"relationship": "HAS_GENE", "source": "Genome", "target": "Gene",
                               "relationship_type": "HAS_RELATIONSHIP",
                               "target_link_type": "HAS_TARGET"})
        assert mr.direction("Genome") == "outgoing"
        assert mr.direction("Gene") == "incoming"

    def test_is_source_required(self):
        mr = Metarelationship({"relationship": "HAS_GENE", "source": "Genome", "target": "Gene",
                               "relationship_type": "REQUIRE_RELATIONSHIP",
                               "target_link_type": "HAS_TARGET"})
        assert mr.is_source_required()
        assert not mr.is_target_required()
        assert not self.mr.is_source_required()

    def test_is_target_required(self):
        mr = Metarelationship({"relationship": "HAS_GENE", "source": "Genome", "target": "Gene",
                               "relationship_type": "HAS_RELATIONSHIP",
                               "target_link_type": "REQUIRE_TARGET"})
        assert mr.is_target_required()
        assert not mr.is_source_required()
        assert not self.mr.is_target_required()

    def test_ontology_label(self):
        mr = Metarelationship({"relationship": "APPLIES_TO", "source": "MetricDefinition",
                               "target": "OntologyNode", "relationship_type": "HAS_RELATIONSHIP",
                               "target_link_type": "HAS_TARGET",
                               "ontology": "gamma-metrics", "ontology_version": "3.27"})
        assert mr.ontology_label() == "gamma-metrics v3.27"
        assert self.mr.ontology_label() == ""


class TestRelationshipRows:
    """A class pointing at its own ancestor must not print twice."""

    @staticmethod
    def _info(lineage, records):
        from neuro.base.schema import (Metarelationship, Metarelationships,
                                       OntologyNodeInfo)
        info = object.__new__(OntologyNodeInfo)
        info.lineage = lineage
        info.metarelationships = Metarelationships(lineage[0])
        for key, record in records:
            info.metarelationships[key] = Metarelationship(record)
        return info

    def test_relationship_rows(self):
        # One declaration, WebVisit -[:OF_SUBJECT]-> Node, collected twice
        # because Node is WebVisit's own ancestor.
        record = {"relationship": "OF_SUBJECT", "source": "WebVisit", "target": "Node",
                  "relationship_type": "HAS_RELATIONSHIP", "target_link_type": "HAS_TARGET",
                  "ontology": "gamma-system", "ontology_version": "3.8"}
        info = self._info(
            ["WebVisit", "Node", "Object"],
            [("OF_SUBJECT:Node:outgoing", record), ("OF_SUBJECT:WebVisit:incoming", record)],
        )
        assert len(info.metarelationships) == 2
        assert info.relationship_rows() == [
            (" ", "Node", "←", "OF_SUBJECT", "WebVisit", "gamma-system v3.8"),
        ]

    def test_relationship_rows_distinct(self):
        outgoing = {"relationship": "ON_PAGE", "source": "WebVisit", "target": "WebPage",
                    "relationship_type": "HAS_RELATIONSHIP", "target_link_type": "HAS_TARGET",
                    "ontology": "gamma-system", "ontology_version": "3.8"}
        incoming = {"relationship": "OF_SUBJECT", "source": "WebVisit", "target": "Node",
                    "relationship_type": "HAS_RELATIONSHIP", "target_link_type": "HAS_TARGET",
                    "ontology": "gamma-system", "ontology_version": "3.8"}
        info = self._info(
            ["WebVisit", "Node", "Object"],
            [("ON_PAGE:WebPage:outgoing", outgoing), ("OF_SUBJECT:Node:outgoing", incoming)],
        )
        assert info.relationship_rows() == [
            (" ", "Node", "←", "OF_SUBJECT", "WebVisit", "gamma-system v3.8"),
            (" ", "WebVisit", "→", "ON_PAGE", "WebPage", "gamma-system v3.8"),
        ]


class TestLineageLines:
    """Multiple inheritance is a DAG; the Lineage block must not flatten it."""

    @staticmethod
    def _info(label, parents):
        from neuro.base.schema import OntologyNodeInfo
        info = object.__new__(OntologyNodeInfo)
        info.label = label
        info.parents = parents
        return info

    def test_lineage_lines_chain(self):
        info = self._info("EntityPage", {
            "EntityPage": ["WebPage"], "WebPage": ["Node"], "Node": ["Object"],
            "Object": [],
        })
        assert info.lineage_lines() == [
            "   EntityPage ➜  WebPage ➜  Node ➜  Object",
        ]

    def test_lineage_lines_branching(self):
        from neuro.utils import terminal_style
        # MissedCall is both a PhoneCall and a Message; Object is reached down
        # both branches and is the same node, so the repeat is dimmed.
        info = self._info("MissedCall", {
            "MissedCall": ["Message", "PhoneCall"], "Message": ["TimePoint"],
            "TimePoint": ["Object"], "PhoneCall": ["Object"], "Object": [],
        })
        dim = f"{terminal_style.DIM}Object{terminal_style.RESET}"
        assert info.lineage_lines() == [
            "   MissedCall",
            "   ├─ Message ➜  TimePoint ➜  Object",
            f"   └─ PhoneCall ➜  {dim}",
        ]

    def test_lineage_lines_nested(self):
        from neuro.utils import terminal_style
        info = self._info("Leaf", {
            "Leaf": ["Left", "Right"], "Left": ["Upper", "Lower"],
            "Upper": ["Object"], "Lower": [], "Right": ["Object"], "Object": [],
        })
        dim = f"{terminal_style.DIM}Object{terminal_style.RESET}"
        assert info.lineage_lines() == [
            "   Leaf",
            "   ├─ Left",
            "   │  ├─ Lower",
            "   │  └─ Upper ➜  Object",
            f"   └─ Right ➜  {dim}",
        ]

    def test_lineage_lines_cycle(self):
        from neuro.utils import terminal_style
        info = self._info("A", {"A": ["B"], "B": ["A"]})
        dim = f"{terminal_style.DIM}A{terminal_style.RESET}"
        assert info.lineage_lines() == [f"   A ➜  B ➜  {dim}"]


def _decl(property_label, property_type, node, required=False):
    return Metaproperty({
        "property": property_label,
        "node": node,
        "node_object": None,
        "property_object": None,
        "property_type": property_type,
        "relationship_type": "HAS_PROPERTY",
        "relationship_lineage": ["HAS_PROPERTY"] + (["REQUIRE_PROPERTY"] if required else []),
        "deep_node": "OntologyNode",
        "distance": 0,
    })


class TestMetapropertiesUnion:
    """Validation across a multi-label node's merged schemas."""

    def _union(self, *declarations):
        union = MetapropertiesUnion(["A", "B"])
        for mp in declarations:
            union[mp.label] = mp
        return union

    def test_property_defined_by_either_label(self):
        union = self._union(_decl("a", "String", "A"), _decl("b", "String", "B"))
        v = union.validate_properties({"a": "x", "b": "y"})
        assert not v
        assert not v.undefined_properties

    def test_undefined_only_when_no_label_declares(self):
        union = self._union(_decl("a", "String", "A"))
        v = union.validate_properties({"a": "x", "ghost": "z"})
        assert v.undefined_properties == ["ghost"]

    def test_conjunction_passes_when_all_declarations_hold(self):
        union = self._union(_decl("c", "String", "A"), _decl("c", "String", "B"))
        v = union.validate_properties({"c": "hello"})
        assert not v

    def test_conjunction_fails_naming_both_declarations(self):
        union = self._union(_decl("name", "String", "Microscope"),
                            _decl("name", "Color", "Thing"))
        v = union.validate_properties({"name": "hello"})
        assert v.invalid_properties
        reason = v.invalid_properties[0][1]
        assert "String (Microscope)" in reason and "Color (Thing)" in reason

    def test_required_is_union_across_labels(self):
        union = self._union(_decl("a", "String", "A"), _decl("b", "String", "B", required=True))
        v = union.validate_properties({"a": "x"})
        assert [p.label for p in v.missing_properties] == ["b"]

    def test_single_label_behaves_as_before(self):
        union = self._union(_decl("a", "String", "A", required=True))
        assert not union.validate_properties({"a": "x"})
        v = union.validate_properties({})
        assert [p.label for p in v.missing_properties] == ["a"]
