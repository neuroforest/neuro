import csv
import json
import logging
import multiprocessing
import urllib.parse

import requests

from neuro.core.tid import Tiddler, TiddlerList
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
        return dict()
    else:
        return data[0]


def get_taxon_tiddler(taxon_id):
    """
    Get a basic taxon tiddler without the fields `neuro.primary` or `tags`.
    :param taxon_id: iNaturalist taxon id
    :return: Tiddler object
    """
    taxon_data = get_taxon(taxon_id)

    # Select title
    taxon_name = taxon_data["name"]
    taxon_rank_level = taxon_data["rank_level"]
    taxon_rank = taxon_data["rank"]
    taxon_ranks_path = internal_utils.get_path("resources") / "data" / "taxon-ranks.csv"
    with open(taxon_ranks_path) as f:
        csv_reader = csv.reader(f)
        next(csv_reader)  # Skip header, assume name,inat.rank.level,encoding
        neuro_code = str()
        for row in csv_reader:
            if str(taxon_rank_level) == row[1] and taxon_rank == row[0]:
                neuro_code = row[2][1:-1]
                break
        if not neuro_code and taxon_rank_level != 100:
            print(f"Taxon not found: {taxon_data['rank']} ({taxon_rank_level})")
            return Tiddler()
    tid_title = f"{neuro_code} {taxon_name}"

    tiddler = Tiddler(tid_title)
    tiddler.add_fields({
        "neuro.role": f"taxon.{taxon_rank}",
        "inat.taxon.id": taxon_id
    })
    return tiddler


def get_taxon_tiddler_list(taxon_id):
    """
    Return a tiddler list with every element in the taxon chain.
    :param taxon_id:
    :return:
    """
    taxon_data = get_taxon(taxon_id)
    if not taxon_data:
        return TiddlerList()
    ancestor_taxon_ids = taxon_data["ancestor_ids"]
    taxon_tiddler_list = TiddlerList()

    # Recruit a pool of workers, every worker making a request for ancestor taxon
    p = multiprocessing.Pool(processes=len(ancestor_taxon_ids))
    with p:
        tiddler_list = p.map(get_taxon_tiddler, ancestor_taxon_ids)
    tiddler_list.append(get_taxon_tiddler(taxon_id))

    for tiddler in tiddler_list:
        if not tiddler:
            continue
        taxon_tiddler_list.append(tiddler)

    return taxon_tiddler_list
