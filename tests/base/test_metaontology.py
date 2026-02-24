"""
Integration tests for neuro.base.metaontology
"""

import pytest

from neuro.utils import exceptions


class TestImport:
    def test_import(self):
        from neuro.base.metaontology import Metaontology  # noqa: F401


@pytest.mark.integration
class TestMetaontology:
    def test_accessor(self, nb):
        assert nb.metaontology is not None

    def test_no_metaontology_raises(self, nb):
        with pytest.raises(exceptions.NoOntology):
            nb.metaontology.is_ontology_valid()