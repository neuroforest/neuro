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
        assert "neuro.id" in mp
        assert mp["neuro.id"].is_required()

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
        nb_meta.run_query("CREATE (:OntologyNode {label: 'Orphan', `neuro.id`: randomUUID()})")
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert violations.disconnected
        violations.disconnected = False
        assert not violations

    def test_undefined_property(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'HasBogus', `neuro.id`: randomUUID(), bogus: 'x'})"
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
            "CREATE (n:OntologyNode {label: 'bad-label', `neuro.id`: randomUUID()})"
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

    def test_invalid_neuro_id(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'BadId', `neuro.id`: 'not-a-uuid-v4'})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("BadId", "OntologyNode")
        assert "neuro.id" in [p for p, _ in v.invalid_properties]
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
        assert "neuro.id" in [p.label for p in v.missing_properties]
        violations.violations.clear()
        assert not violations
