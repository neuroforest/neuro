import os
from pathlib import Path

import requests

from neuro.utils import exceptions


WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"


def _user_agent():
    """`<app>/<version> (<url>)`, as Wikidata's policy asks. The app's version is
    the VERSION file in APP_DIR (PLAN-2026-322: APP_VERSION left the environment
    when the file became the one literal); without an app dir, or without the
    file, neuro's own version stands in. Never a KeyError at import: the pipeline
    scripts import this module on a host that sets no APP_* at all."""
    name = os.environ.get("APP_NAME", "NeuroForest")
    url = os.environ.get("APP_URL", "https://github.com/neuroforest")
    version = ""
    app_dir = os.environ.get("APP_DIR")
    if app_dir:
        try:
            version = (Path(app_dir) / "VERSION").read_text().strip()
        except OSError:
            version = ""
    if not version:
        from neuro import __version__
        version = __version__
    return f"{name}/{version} ({url})"


HEADERS = {"User-Agent": _user_agent()}


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
