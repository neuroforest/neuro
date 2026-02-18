"""
Tests for the package neuro.tools.integrations
"""

import pytest


pytestmark = pytest.mark.e2e


class TestGbif:
    def test_request_get(self):
        from neuro.tools.integrations import gbif
        taxon_data = gbif.get_taxon("2597892")
        assert taxon_data["species"] == "Penicillium digitatum"
        assert taxon_data["familyKey"] == 3563703


class TestInaturalist:
    def test_request_get(self):
        from neuro.tools.integrations import inaturalist

        observation_data = inaturalist.get_observation("67294836")
        assert observation_data["uuid"] == "275460f4-6fe0-4991-bfd5-991bff22697b"

        taxon_data = inaturalist.get_taxon(109281)
        assert taxon_data["name"] == "Phengaris arion"


class TestNCBI:
    def test_resolve_taxon_name(self):
        from neuro.tools.integrations import ncbi
        taxon_ids = ncbi.resolve_taxon_name("Amata phegea")
        assert len(taxon_ids) == 1
        assert taxon_ids[0] == "938170"
        taxon_ids = ncbi.resolve_taxon_name("Proteus")
        assert len(taxon_ids) == 2
        taxon_ids = ncbi.resolve_taxon_name("Protozoa")
        assert len(taxon_ids) == 0

    def test_get_lineage(self):
        from neuro.tools.integrations import ncbi
        lineage = ncbi.get_lineage("938170")
        lepidoptera = {
            "TaxId": "7088",
            "ScientificName": "Lepidoptera",
            "Rank": "order"
        }
        assert lepidoptera in lineage

    def test_get_taxon_info(self):
        from neuro.tools.integrations import ncbi
        taxon_info = ncbi.get_taxon_info("938170")
        assert taxon_info["ScientificName"] == "Amata phegea"


class TestWikiData:
    def test_fetch(self, test_file):
        from neuro.tools.integrations import wikidata
        params = {
            "entity-id": "Q1285940"
        }
        query_file_path = test_file.get_resource("queries/test.rq")
        data = wikidata.fetch(query_file_path, params)
        assert data
        assert data[0]["organismLabel"]["value"] == "Scatophagus"


class TestZotero:
    def test_get_citation_text(self):
        """
        Using this open Zotero group for testing:
        https://www.zotero.org/groups/368553/aquacrop_publications
        """
        from neuro.tools.integrations import zotero
        item_id = "PJRUXIWH"
        library_id = "368553"
        library_type = "group"
        citation_text = zotero.get_citation_text(item_id, library_id, library_type=library_type, style="apa")
        assert citation_text
        assert len(citation_text) == 246
