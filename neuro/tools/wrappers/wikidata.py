import logging
import requests

from neuro.utils import internal_utils
from neuro.core.data.dict import  DictUtils

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
FIELD_MAP = {
    "taxon": "taxonRank",
    "trans.slv": "labelSL",
    "trans.eng": "labelEN",
    "inat.taxon.id": "iNaturalistID",
    "gbif.taxon.id": "gbifID",
    "taxon.parent": "parentTaxon",
    "name": "taxonName"
}


def get_query(file_name):
    """
    Get a Wikidata query from `resources` according to file name.
    :param file_name:
    :return: string
    """
    folder_name = internal_utils.get_path("wd_queries")
    query_file = f"{folder_name}/{file_name}.rq"
    with open(query_file) as f:
        query = f.read()
    return query


def send_query(query: str, wikidata_sparql_url: str = WIKIDATA_SPARQL_URL):
    """
    Send a SPARQL query and return the JSON formatted result.

    Inspired by https://qwikidata.readthedocs.io/en/stable/_modules/qwikidata/sparql.html

    :param query: SPARQL query string
    :param wikidata_sparql_url: wikidata SPARQL endpoint to use
    :return: json response
    :rtype: dict
    """
    res = requests.get(wikidata_sparql_url, params={"query": query, "format": "json"})
    return res.json()


def get_taxon_data(taxon_name):
    """
    Get taxon data form WikiData and convert it to tiddler format.
    :param taxon_name:
    :return: intermediate tiddler-like dictionary
    """
    query_template = get_query("organism")
    wikidata_query = query_template.replace("_organism_", taxon_name)
    res = send_query(wikidata_query)

    if not res["results"]["bindings"]:
        logging.warning(f"Data for taxon not found: {taxon_name}")
        return False
    else:
        bindings = res["results"]["bindings"][0]

    data = {
        "name": taxon_name,
    }

    for field_neuro, field_wikidata in FIELD_MAP.items():
        if field_wikidata not in bindings:
            continue
        else:
            data[field_neuro] = bindings[field_wikidata]["value"]

    return data
