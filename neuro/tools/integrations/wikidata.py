import os
import requests

from neuro.utils import exceptions


WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": f"{os.environ['APP_NAME']}/{os.environ['APP_VERSION']} ({os.environ['APP_URL']})"}


def fetch(query_file_path, params: dict = None, wikidata_sparql_url=WIKIDATA_SPARQL_URL):
    """
    Query Wikidata using a template from `resources` according to file name.
    Inspired by https://qwikidata.readthedocs.io/en/stable/_modules/qwikidata/sparql.html
    :param query_file_path:
    :param params: dict
    :param wikidata_sparql_url: wikidata SPARQL endpoint to use
    :return: JSON response
    :rtype: dict
    """
    with open(query_file_path) as f:
        query = f.read()

    if params:
        for parameter, value in params.items():
            query = query.replace(f"_{parameter}_", value)

    res = requests.get(wikidata_sparql_url, params={"query": query, "format": "json"},
                        headers=HEADERS)
    if res.status_code == 200:
        return res.json()["results"]["bindings"]
    else:
        raise exceptions.UnhandledStatusCode(f"{res.status_code} {res.reason} {res.text}")
