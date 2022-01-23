"""
Command `neuro taxon <taxon_name>`, where the argument taxon_name is
the scientific name of the taxon.
"""
import logging

import click
import halo

from neuro.core import tid
from neuro.tools.api import tw_get, tw_put
from neuro.tools.wrappers import gbif, inaturalist, wikidata

from neuro.tools.terminal import components
from neuro.tools.terminal import style
from neuro.tools.terminal.cli import pass_environment

logging.basicConfig(level=30)


OBLIGATORY_TAXA = [
    "taxon.kingdom",
    "taxon.phylum",
    "taxon.class",
    "taxon.order",
    "taxon.family",
    "taxon.genus",
    "taxon.species"
]

REPLACE = {
    ".bt-k Bacteria": [".bt-d Bacteria", "taxon.domain"],
    ".bt-k Viruses": [".bt-d Viridae", "taxon.domain"],
    ".bt-p Actinobacteriota": [".bt-p Actinobacteria", "taxon.phylum"]
}


def filter_neuro_tids(neuro_tids):
    """
    Filter and repair neuro_tids.
    :return: True | False
    """
    filtered_neuro_tids = tid.NeuroTids()
    for neuro_tid in neuro_tids:
        # Replace certain titles
        tid_title = neuro_tid.title
        if tid_title in REPLACE:
            neuro_tid.title = REPLACE[tid_title]
            neuro_tid.fields["neuro.role"] = REPLACE[tid_title]
        tid_title = neuro_tid.title = neuro_tid.title

        if neuro_tid.fields["neuro.role"] in OBLIGATORY_TAXA:
            filtered_neuro_tids.append(neuro_tid)
        else:
            # Not implemented - later irrelevant
            if tw_get.is_tiddler(tid_title):
                tiddler = tw_get.tiddler(tid_title)
                neuro_tid.add_fields(tiddler, overwrite=False)
                filtered_neuro_tids.append(neuro_tid)
    return filtered_neuro_tids


def get_wikidata_data(taxon_name):
    """
    Get and repair data from WikiData
    :param taxon_name:
    :return:
    """
    data = wikidata.get_taxon_data(taxon_name)
    if "tans.slv" in data:
        data["trans.slv"] = data["trans.slv"].lower()
    try:
        if data["trans.eng"] == data["name"]:
            del data["trans.eng"]
    except KeyError:
        pass
    return data


@click.command("taxon", short_help="Organism.")
@click.argument("taxon_name", required=True, nargs=-1)
@pass_environment
def cli(ctx, taxon_name):
    """
    Command `neuro taxon <taxon_name>`
    By running this command taxon-specific web scraping is performed
    to gather data from WikiData, iNaturalist and GBIF. Besides the requested
    taxon, its full taxon chain is added to the NeuroForest wiki.

    :Example:
    ➜ neuro taxon Carlito syrichta

    :param ctx:
    :param taxon_name: scientific name of the taxon
    :return:
    """
    spinner = halo.Halo(text="Gathering taxon data...", spinner="dots")
    spinner.start()
    taxon_name = " ".join(taxon_name).strip()

    # Get the initial identification data
    data = get_wikidata_data(taxon_name)
    if "gbif.taxon.id" not in data:
        gbif_taxon_id = gbif.search_by_name(taxon_name)
        if gbif_taxon_id:
            data["gbif.taxon.id"] = gbif_taxon_id

    if not data:
        spinner.stop_and_persist(symbol=style.FAIL, text=f"{taxon_name}: WikiData no entity")
        return
    elif "inat.taxon.id" in data:
        inaturalist_taxon_id = data["inat.taxon.id"]
        neuro_tids = inaturalist.get_taxon_tids(inaturalist_taxon_id)
        neuro_tids[-1].add_fields(data)
        neuro_tids = filter_neuro_tids(neuro_tids)
        spinner.stop_and_persist(symbol=style.SUCCESS, text=f"{taxon_name}: iNaturalist data")
    elif "gbif.taxon.id" in data:
        neuro_tids = gbif.get_taxon_tids(data["gbif.taxon.id"])
        neuro_tids[-1].add_fields(data)
        neuro_tids = filter_neuro_tids(neuro_tids)
        spinner.stop_and_persist(symbol=style.SUCCESS, text=f"{taxon_name}: GBIF data")
    else:
        spinner.stop_and_persist(symbol=style.FAIL, text="Data could not be gathered")
        return

    # Exclude irrelevant
    neuro_tids.chain()
    relevant = [neuro_tid for neuro_tid in neuro_tids if not tw_get.is_tiddler(neuro_tid.title)]

    # Put relevant into the wiki
    if relevant:
        for neuro_tid in relevant:
            if components.bool_prompt(f"Put tiddler {neuro_tid.title}?"):
                tw_put.neuro_tid(neuro_tid)
    else:
        print("Nothing to add.")
