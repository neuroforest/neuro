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
    def test_no_metaontology_raises(self, nb):
        with pytest.raises(exceptions.NoOntology):
            nb.metaontology.is_ontology_valid()

