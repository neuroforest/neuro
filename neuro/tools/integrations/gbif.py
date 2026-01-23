"""
Global Biodiversity Information Facility (GBIF) API wrapper.
"""

import csv
import json
import multiprocessing
import requests
import urllib.parse

from neuro.core import tid
from neuro.utils import exceptions, internal_utils


FIELD_MAP = {
    "canonicalName": "name",
    "vernacularName": "trans.eng"
}


def request_get(endpoint):
    gbif_api = "https://api.gbif.org/v1/"
    url = urllib.parse.urljoin(gbif_api, endpoint)
    res = requests.get(url)
    status_code = res.status_code
    if status_code == 200:
        return res.text
    elif status_code == 404:
        raise exceptions.InvalidURL(url)
    else:
        raise exceptions.UnhandledStatusCode(str(status_code))


def get_taxon(taxon_id):
    response_text = request_get(f"species/{taxon_id}")
    taxon_data = json.loads(response_text)
    return taxon_data


def search_by_name(scientific_name):
    params = {"name": scientific_name}
    endpoint = f"species/match?{urllib.parse.urlencode(params)}"
    response_text = request_get(endpoint)
    taxon_data = json.loads(response_text)
    if "usageKey" in taxon_data:
        return taxon_data["usageKey"]
    else:
        return False


def collect_fields(data, field_list, transform=False):
    """
    Collect fields from data returned.
    :param data:
    :param field_list:
    :param transform:
    :return:
    """
    if transform:
        fields = dict()
        for gbif_field in field_list:
            if gbif_field in data:
                field = FIELD_MAP[gbif_field]
                fields[field] = data[gbif_field]
        return fields
    else:
        value_list = list()
        for gbif_field in field_list:
            if gbif_field in data:
                value_list.append(data[gbif_field])
        return value_list


def get_taxon_tid(taxon_id):
    """
    Get an instance of Tiddler that hold the parsed data.
    :param taxon_id: GBIF taxon id
    :return:
    """
    taxon_data = get_taxon(taxon_id)

    # Select title
    try:
        taxon_name = taxon_data["canonicalName"]
    except KeyError:
        taxon_name = taxon_data["scientificName"]
    taxon_rank = taxon_data["rank"].lower()
    taxon_ranks_path = internal_utils.get_path("resources") + "/data/taxon-ranks.csv"
    with open(taxon_ranks_path) as f:
        csv_reader = csv.reader(f)
        next(csv_reader)  # Skip header, assume name,inat.rank.level,encoding
        neuro_code = str()
        for row in csv_reader:
            if taxon_rank == row[0]:
                neuro_code = row[2][1:-1]
                break
    tid_title = f"{neuro_code} {taxon_name}"

    neuro_tid = tid.Tiddler(tid_title)
    fields = collect_fields(taxon_data, ["canonicalName", "vernacularName"], transform=True)
    neuro_tid.add_fields({
        **fields,
        "neuro.role": f"taxon.{taxon_rank}",
        "gbif.taxon.id": taxon_id
    })
    return neuro_tid


def get_taxon_tids(taxon_id):
    taxon_data = get_taxon(taxon_id)

    # Extract ancestor gbif taxon ids
    ancestor_taxon_ids = collect_fields(taxon_data, [
        "kingdomKey",
        "phylumKey",
        "classKey",
        "orderKey",
        "familyKey",
        "genusKey",
        "speciesKey"
    ])

    p = multiprocessing.Pool(processes=len(ancestor_taxon_ids))
    with p:
        neuro_tid_list = p.map(get_taxon_tid, ancestor_taxon_ids)

    neuro_tids = tid.TiddlerList()
    for neuro_tid in neuro_tid_list:
        if not neuro_tid:
            continue
        neuro_tids.append(neuro_tid)

    return neuro_tids
