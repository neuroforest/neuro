"""
Unit tests for the package .
"""
import pytest
import json

from ..helper import get_test_file, get_resource_path


def get_inaturalist_mocks():
    from neuro.tools.wrappers import inaturalist
    observation_data = inaturalist.get_observation(67294836)
    observation_data_path = get_test_file("mocks/inaturalist-observation.json", exists=False)
    with open(observation_data_path, "w+") as f:
        json.dump(observation_data, f)

    taxon_data = inaturalist.get_taxon(109281)
    taxon_data_path = get_test_file("mocks/inaturalist-taxon.json", exists=False)
    with open(taxon_data_path, "w+") as f:
        json.dump(taxon_data, f)


class TestInaturalist:
    @pytest.mark.integration
    def test_request_get(self):
        from neuro.tools.wrappers import inaturalist

        observation_data = inaturalist.get_observation("67294836")
        assert observation_data["uuid"] == "275460f4-6fe0-4991-bfd5-991bff22697b"

        taxon_data = inaturalist.get_taxon(109281)
        assert taxon_data["name"] == "Phengaris arion"


class TestWikiData:
    @pytest.mark.integration
    def test_query(self):
        from neuro.tools.wrappers import wikidata
        query_path = get_resource_path("queries/test.rq")
        with open(query_path) as f:
            query = f.read()
        data = wikidata.send_query(query)
        result = data["results"]["bindings"][0]
        assert result["label"]["xml:lang"] == "en"
        assert result["label"]["value"] == "test"


class TestGbif:
    @pytest.mark.integration
    def test_request_get(self):
        from neuro.tools.wrappers import gbif
        taxon_data = gbif.get_taxon("2597892")
        assert taxon_data["species"] == "Penicillium digitatum"
        assert taxon_data["familyKey"] == 3563703
