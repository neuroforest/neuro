import logging
import requests

from neuro.utils import internal_utils, exceptions


WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
FIELD_MAP = {
    "trans.slv": "labelSL",
    "trans.eng": "labelEN",
    "inat.taxon.id": "iNaturalistID",
    "gbif.taxon.id": "gbifID",
    "name": "taxonName"
}


def get_query(file_name, params: dict = None):
    """
    Get a Wikidata query from `resources` according to file name.
    :param file_name:
    :param params: dict
    :return: string
    """
    folder_name = internal_utils.get_path("wd_queries")
    query_file = f"{folder_name}/{file_name}.rq"
    with open(query_file) as f:
        query = f.read()

    # Parameter substitution
    if params:
        for parameter, value in params.items():
            query = query.replace(f"_{parameter}_", value)

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
    if res.status_code == 200:
        return res.json()
    else:
        raise exceptions.UnhandledStatusCode(f"{res.status_code} {res.reason}")


def get_taxon_data(taxon_name: str):
    """
    Get taxon data form WikiData and convert it to tiddler format.
    :param taxon_name:
    :return: intermediate tiddler-like dictionary
    """
    if not taxon_name:
        logging.warning("Taxon name not given.")
        return {}

    query = get_query("taxon", {"taxon": taxon_name})
    res = send_query(query)

    if not res["results"]["bindings"]:
        logging.info(f"Data for taxon not found: {taxon_name}")
        return {}
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
