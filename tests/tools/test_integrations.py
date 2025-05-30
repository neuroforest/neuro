"""
Unit tests for the package .
"""
import pytest
import json

from ..helper import get_test_file, get_path


def get_inaturalist_mocks():
    from neuro.tools.integrations import inaturalist
    observation_data = inaturalist.get_observation(67294836)
    observation_data_path = get_test_file("mocks/inaturalist-observation.json", exists=False)
    with open(observation_data_path, "w+") as f:
        json.dump(observation_data, f)

    taxon_data = inaturalist.get_taxon(109281)
    taxon_data_path = get_test_file("mocks/inaturalist-taxon.json", exists=False)
    with open(taxon_data_path, "w+") as f:
        json.dump(taxon_data, f)


class TestGbif:
    @pytest.mark.integration
    def test_request_get(self):
        from neuro.tools.integrations import gbif
        taxon_data = gbif.get_taxon("2597892")
        assert taxon_data["species"] == "Penicillium digitatum"
        assert taxon_data["familyKey"] == 3563703


class TestInaturalist:
    @pytest.mark.integration
    def test_request_get(self):
        from neuro.tools.integrations import inaturalist

        observation_data = inaturalist.get_observation("67294836")
        assert observation_data["uuid"] == "275460f4-6fe0-4991-bfd5-991bff22697b"

        taxon_data = inaturalist.get_taxon(109281)
        assert taxon_data["name"] == "Phengaris arion"


class TestNCBI:
    @pytest.mark.integration
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
    @pytest.mark.integration
    def test_fetch(self):
        from neuro.tools.integrations import wikidata
        params = {
            "entity-id": "Q1285940"
        }
        query_file_path = get_path("resources/queries/test.rq")
        data = wikidata.fetch(query_file_path, params)
        assert data
        assert data[0]["organismLabel"]["value"] == "Scatophagus"


class TestZotero:
    @pytest.mark.integration
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
