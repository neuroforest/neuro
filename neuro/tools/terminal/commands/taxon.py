"""
Command `neuro taxon <taxon_name>`, where the argument taxon_name is
the scientific name of the taxon.
"""
import logging
import subprocess
import os.path
import sys

import click
import halo

from neuro.core import tid
from neuro.tools.api import tw_api, tw_get, tw_put
from neuro.tools.wrappers import gbif, inaturalist, wikidata

from neuro.tools.terminal import components
from neuro.tools.terminal import style
from neuro.tools.terminal.cli import pass_environment

logging.basicConfig(level=30)


OBLIGATORY_TAXA = [
    "taxon.domain",
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
    ".bt-p Actinobacteriota": [".bt-p Actinobacteria", "taxon.phylum"],
    ".bt-p Bacteroidetes": [".bt-p Bacteroidota", "taxon.phylum"],
    ".bt-p Firmicutes_A": [".bt-p Firmicutes", "taxon.phylum"],
    ".bt-p Firmicutes_B": [".bt-p Firmicutes", "taxon.phylum"],
    ".bt-p Methanobacteriota_A": [".bt-p Methanobacteriota", "taxon.phylum"],
    ".bt-p Miozoa": [".bt-p Myzozoa", "taxon.phylum"],
    ".bt-p Spirochaetes": [".bt-p Spirochaetota", "taxon.phylum"],
    ".bt-p Spirochaetae": [".bt-p Spirochaetota", "taxon.phylum"],
    ".bt-c Bacteroidia": [".bt-c Bacteroidia", "taxon.phylum"],
    ".bt-o Caudata": [".bt-o Urodela", "taxon.order"],
    ".bt-o Enterobacteriales": [".bt-o Enterobacterales", "taxon.order"]
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
            neuro_tid.title = REPLACE[tid_title][0]
            neuro_tid.fields["neuro.role"] = REPLACE[tid_title][1]
        tid_title = neuro_tid.title

        if neuro_tid.fields["neuro.role"] in OBLIGATORY_TAXA:
            filtered_neuro_tids.append(neuro_tid)
        else:
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
    if "trans.slv" in data:
        data["trans.slv"] = data["trans.slv"].lower()
    try:
        if data["trans.eng"] == data["name"]:
            del data["trans.eng"]
    except KeyError:
        pass
    return data


def integrate_wiki_filesystem(local):
    if not local:
        print("Error: no local filesystem root provided")
        return

    # Find non-integrated taxa
    tw_filter = "[prefix[.bt-]!has[local]]"
    tw_fields = ["title", "neuro.role"]
    fields_list = tw_get.tw_fields(tw_fields, tw_filter)

    def has_taxon_integrity(taxon_fields):
        if "neuro.role" not in taxon_fields:
            print(f"Error: tiddler {fields['title']} has no field 'neuro.role'")
            return False
        else:
            return True

    # Filter according to data integrity and obligatory taxa
    fields_list = [fields for fields in fields_list if has_taxon_integrity(fields)]
    fields_list = [fields for fields in fields_list if fields["neuro.role"] in OBLIGATORY_TAXA]

    fail_count = 0
    for fields in fields_list:
        taxon_name = "_".join(fields["title"].split(" ")[1:])
        p = subprocess.Popen(["find", local, "-type", "d", "-name", taxon_name], stdout=subprocess.PIPE)
        p.wait()
        path = p.communicate()[0].decode("utf-8")[:-1]
        p.kill()

        if not path:
            fail_count += 1
            continue
        elif path.count("\n") > 0:
            fail_count += 1
            print(f"{style.FAIL} Multiple directories named '{taxon_name}'")
            continue

        path = f"file://{path}"
        res = tw_put.fields({"title": fields["title"], "local": path})
        if res.status_code == 204:
            print(f"{style.SUCCESS} {taxon_name.replace('_', ' ')}")
        else:
            print(f"{style.FAIL} {taxon_name.replace('_', ' ')}")

    print(f"Path not resolved for {fail_count} items")


@click.command("taxon", short_help="import taxon")
@click.argument("taxon_name", nargs=-1)
@click.option("-l", "--local", default="")
@click.option("-i", "--integrate", is_flag=True)
@pass_environment
def cli(ctx, taxon_name, local, integrate):
    """
    Command `neuro taxon <taxon_name>`.
    By running this command taxon-specific web scraping is performed
    to gather data from WikiData, iNaturalist and GBIF. Besides the requested
    taxon, its full taxon chain is added to the NeuroWiki.

    :Example:
    $ neuro taxon Carlito syrichta

    :param ctx:
    :param taxon_name: scientific name of the taxon
    :param local: path to local organism file tree
    :param integrate: integrate NeuroWiki with local filesystem
    :return:
    """
    if not tw_api.get_api():
        return

    # Handle integration of NeuroWiki with local filesystem
    if integrate:
        integrate_wiki_filesystem(local)
        return

    if not taxon_name:
        print("Error: no taxon name given")
        sys.exit()

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
        if not neuro_tids:
            spinner.stop_and_persist(symbol=style.FAIL, text=f"{taxon_name}: Incorrect iNaturalist ID on WikiData")
            return
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
            if components.bool_prompt(f"Put tiddler \"{neuro_tid.title}\"?"):
                tw_put.neuro_tid(neuro_tid)
    else:
        print("No additions to NeuroWiki.")

    # Create local file tree
    local_relevant = [neuro_tid for neuro_tid in neuro_tids if neuro_tid.fields["neuro.role"] in OBLIGATORY_TAXA]
    added = False
    if local_relevant and local:
        current_path = local
        for neuro_tid in local_relevant:
            name = neuro_tid.title.split(" ", 1)[1].replace(" ", "_")
            current_path = f"{current_path}/{name}"
            if not os.path.isdir(current_path):
                added = True
                subpath = current_path.replace(f"{local}/", "")
                if components.bool_prompt(f"Establish subpath \"{subpath}\"?"):
                    os.mkdir(current_path)
                    neuro_tid.fields["local"] = f"file://{current_path}"
                    tw_put.neuro_tid(neuro_tid)
                else:
                    break
    if not added:
        print("No additions to local file system.")
