"""
Integration tests for neuro.base.metaontology
"""

import pytest

from neuro.utils import exceptions


class TestImport:
    def test_import(self):
        from neuro.base.metaontology import Metaontology  # noqa: F401


class TestMetaontology:
    def test_accessor(self, nb):
        assert nb.metaontology is not None

    def test_metaproperties(self, nb_meta):
        from neuro.base.schema import Metaproperties
        mp = Metaproperties.from_ontology(nb_meta, "Node")
        assert "nid" in mp
        assert mp["nid"].is_required()

    def test_metaontology(self, nb_meta):
        result = nb_meta.metaontology.is_ontology_valid()
        if not result:
            print(nb_meta.metaontology.violations)
        assert result


class TestOntologyValidator:
    def test_no_ontology_raises(self, nb):
        with pytest.raises(exceptions.NoOntology):
            nb.metaontology.is_ontology_valid()

    def test_disconnected_ontology(self, nb_meta):
        nb_meta.run_query("CREATE (:OntologyNode {label: 'Orphan', nid: randomUUID()})")
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert violations.disconnected
        violations.disconnected = False
        assert not violations

    def test_undefined_property(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'HasBogus', nid: randomUUID(), bogus: 'x'})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("HasBogus", "OntologyNode")
        assert "bogus" in v.undefined_properties
        violations.violations.clear()
        assert not violations

    def test_invalid_label(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'bad-label', nid: randomUUID()})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("bad-label", "OntologyNode")
        assert "label" in [p for p, _ in v.invalid_properties]
        violations.violations.clear()
        assert not violations

    def test_invalid_nid(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'BadId', nid: 'not-a-uuid-v4'})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("BadId", "OntologyNode")
        assert "nid" in [p for p, _ in v.invalid_properties]
        violations.violations.clear()
        assert not violations

    def test_missing_property(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'NoId'})-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("NoId", "OntologyNode")
        assert "nid" in [p.label for p in v.missing_properties]
        violations.violations.clear()
        assert not violations


class TestPropertyOverrides:
    """Property name conflicts across SUBCLASS_OF lineage.

    Each test scaffolds: A (root) → B (subclass), gives both an `id` property
    via some HAS_PROPERTY-family relationship + property-type pair, and asserts
    the validator's verdict per the covariance matrix.
    """

    @staticmethod
    def _scaffold(nb, b_rel, b_type):
        """Create A.id (HAS_PROPERTY String) and B.id (b_rel b_type), with
        B SUBCLASS_OF A. Assumes b_type already exists in metaontology
        (e.g. 'String') or creates it as a subclass of String.
        """
        nb.run_query(
            f"""
            MATCH (node_root:OntologyNode {{label: 'Node'}})
            MATCH (str:OntologyNode {{label: 'String'}})
            MERGE (op_subtype:OntologyNode {{label: $b_type}})
                ON CREATE SET op_subtype.nid = randomUUID()
            MERGE (op_subtype)-[:SUBCLASS_OF]->(str)
            CREATE (a:OntologyNode {{label: 'A', nid: randomUUID()}})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {{label: 'B', nid: randomUUID()}})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {{label: 'id', nid: randomUUID()}})
            CREATE (a)-[:HAS_PROPERTY]->(a_id)
            CREATE (b_id:{b_type} {{label: 'id', nid: randomUUID()}})
            """,
            {"b_type": b_type},
        )
        nb.run_query(
            f"MATCH (b:OntologyNode {{label: 'B'}}) "
            f"MATCH (b_id:{b_type} {{label: 'id'}}) "
            f"CREATE (b)-[:{b_rel}]->(b_id)"
        )

    def test_covariant_override_silent(self, nb_meta):
        """B.id (HAS_KEY NarrowId) overrides A.id (HAS_PROPERTY String).
        NarrowId is a subclass of String → both dimensions narrow → OK, silent."""
        from neuro.base.metaontology import OntologyValidator
        self._scaffold(nb_meta, b_rel="HAS_KEY", b_type="NarrowId")
        nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert v.override_violations == []
        assert v.override_warnings == []
        validator = OntologyValidator(nb_meta)
        matches = [r for r in validator._find_property_overrides()
                   if r["class_label"] == "B" and r["prop_name"] == "id"]
        assert len(matches) == 1
        assert matches[0]["rel_relation"] == "narrower"
        assert matches[0]["type_relation"] == "narrower"
        assert validator._classify_override(matches[0]) == "ok"

    def test_pure_redeclaration_warns(self, nb_meta):
        """B.id (HAS_PROPERTY String) duplicates A.id (HAS_PROPERTY String).
        Same on both dimensions → warning."""
        self._scaffold(nb_meta, b_rel="HAS_PROPERTY", b_type="String")
        nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert v.override_violations == []
        assert len(v.override_warnings) == 1
        w = v.override_warnings[0]
        assert (w["class_label"], w["ancestor_label"], w["prop_name"]) == ("B", "A", "id")
        assert w["rel_relation"] == "same" and w["type_relation"] == "same"

    def test_relationship_widens_violates(self, nb_meta):
        """Cannot widen the relationship type — invert the lineage so A
        attaches via HAS_KEY and B widens to HAS_PROPERTY. → violation."""
        nb_meta.run_query(
            """
            MATCH (node_root:OntologyNode {label: 'Node'})
            MATCH (str:OntologyNode {label: 'String'})
            CREATE (a:OntologyNode {label: 'A', nid: randomUUID()})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {label: 'B', nid: randomUUID()})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {label: 'id', nid: randomUUID()})
            CREATE (a)-[:HAS_KEY]->(a_id)
            CREATE (b_id:String {label: 'id', nid: randomUUID()})
            CREATE (b)-[:HAS_PROPERTY]->(b_id)
            """
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert len(v.override_violations) == 1
        ov = v.override_violations[0]
        assert ov["rel_relation"] == "wider"

    def test_type_widens_violates(self, nb_meta):
        """B.id (HAS_PROPERTY GenericProp) where GenericProp is a parent of
        String. → type widens → violation."""
        nb_meta.run_query(
            """
            MATCH (node_root:OntologyNode {label: 'Node'})
            MATCH (str:OntologyNode {label: 'String'})
            MATCH (op_root:OntologyNode {label: 'OntologyProperty'})
            CREATE (gp:OntologyNode {label: 'GenericProp', nid: randomUUID()})
                -[:SUBCLASS_OF]->(op_root)
            CREATE (str)-[:SUBCLASS_OF]->(gp)
            CREATE (a:OntologyNode {label: 'A', nid: randomUUID()})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {label: 'B', nid: randomUUID()})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {label: 'id', nid: randomUUID()})
            CREATE (a)-[:HAS_PROPERTY]->(a_id)
            CREATE (b_id:GenericProp {label: 'id', nid: randomUUID()})
            CREATE (b)-[:HAS_PROPERTY]->(b_id)
            """
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert len(v.override_violations) == 1
        ov = v.override_violations[0]
        assert ov["type_relation"] == "wider"

    def test_unrelated_type_violates(self, nb_meta):
        """B.id is typed SiblingType — a fresh subclass of OntologyProperty
        sitting parallel to the String lineage. → unrelated → violation."""
        nb_meta.run_query(
            """
            MATCH (node_root:OntologyNode {label: 'Node'})
            MATCH (op_root:OntologyNode {label: 'OntologyProperty'})
            CREATE (sibling:OntologyNode {label: 'SiblingType', nid: randomUUID()})
                -[:SUBCLASS_OF]->(op_root)
            CREATE (a:OntologyNode {label: 'A', nid: randomUUID()})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {label: 'B', nid: randomUUID()})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {label: 'id', nid: randomUUID()})
            CREATE (a)-[:HAS_PROPERTY]->(a_id)
            CREATE (b_id:SiblingType {label: 'id', nid: randomUUID()})
            CREATE (b)-[:HAS_PROPERTY]->(b_id)
            """
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert len(v.override_violations) == 1
        ov = v.override_violations[0]
        assert ov["type_relation"] == "unrelated"
