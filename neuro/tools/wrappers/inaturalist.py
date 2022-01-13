import csv
import json
import logging
import requests
import urllib.parse

from neuro.core.tid import NeuroTid, NeuroTids
from neuro.utils import exceptions, internal_utils


def request_get(endpoint: str, params: dict, **kwargs):
    """
    Make an API call to iNaturalist API.
    Reference: https://www.inaturalist.org/pages/api+reference

    :param endpoint: API endpoint
    :param params:
    :param kwargs:
    :return: data dict
    """
    inaturalist_api = "https://api.inaturalist.org/v1/"
    url = urllib.parse.urljoin(inaturalist_api, endpoint)
    headers = {'Accept': 'application/json'}

    res = requests.get(url, params, headers=headers, **kwargs)
    status_code = res.status_code
    if status_code == 200:
        data: list = json.loads(res.text)["results"]
        return data
    elif status_code == 404:
        raise exceptions.InvalidURL(url)
    else:
        raise exceptions.UnhandledStatusCode(str(status_code))


def get_observation(observation_id, **kwargs):
    endpoint = f"observations/{observation_id}"
    data = request_get(endpoint, kwargs.get("params", {}))
    return data[0]


def get_taxon(taxon_id, **kwargs):
    endpoint = f"taxa/{taxon_id}"
    data = request_get(endpoint, kwargs.get("params", {}))
    if len(data) == 0:
        logging.error(f"No data found for taxon {taxon_id}")
    else:
        return data[0]


def get_taxon_tid(taxon_id):
    """
    Get basic taxon tid, without the fields `neuro.primary` or `tags`.
    :param taxon_id: iNaturalist taxon id
    :return: NeuroTid object
    """
    taxon_data = get_taxon(taxon_id)

    # Select title.
    taxon_name = taxon_data["name"]
    taxon_rank = taxon_data["rank_level"]
    taxon_ranks_path = internal_utils.get_path("resources") + "/data/taxon-ranks.csv"
    with open(taxon_ranks_path) as f:
        csv_reader = csv.reader(f)
        header = next(csv_reader)  # Assume name,inat.rank.level,encoding
        neuro_code = str()
        for row in csv_reader:
            if str(taxon_rank) == row[1] and taxon_data["rank"] == row[0]:
                neuro_code = row[2][1:-1]
                break
        if not neuro_code:
            print(f"Taxon not found: {taxon_rank}")
            return NeuroTid()

    tid_title = f"{neuro_code} {taxon_name}"
    neuro_tid = NeuroTid(tid_title)
    return neuro_tid


def get_taxon_tids(taxon_id):
    """
    Return a NeuroTids object, that contains tiddler for every element in the taxon chain.
    :param taxon_id:
    :return:
    """
    taxon_data = get_taxon(taxon_id)
    ancestor_taxon_ids = taxon_data["ancestor_ids"]
    neuro_tids = NeuroTids()
    for ancestor_taxon_id in ancestor_taxon_ids:
        neuro_tid = get_taxon_tid(ancestor_taxon_id)
        if neuro_tid:
            neuro_tids.append(neuro_tid)

    return neuro_tids


if __name__ == "__main__":
    get_taxon_tids(57489)