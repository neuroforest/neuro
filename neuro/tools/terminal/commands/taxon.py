"""
Command `neuro taxon <taxon_name>`, where the argument taxon_name is
the scientific name of the taxon.
"""
import logging
import os
import subprocess

import click
import halo

from neuro.core.tid import NeuroTids, NeuroTid
from neuro.core.data.dict import DictUtils
from neuro.tools.api import tw_api, tw_get, tw_put
from neuro.tools.science import biology
from neuro.tools.wrappers import wikidata, ncbi
from neuro.utils import exceptions

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


def process_ncbi_lineage(ncbi_lineage):
    lineage_data = list()
    for taxon in ncbi_lineage:
        prefix = biology.get_prefix(taxon["Rank"])
        if not prefix:
            continue
        tid_title = f"{prefix} {taxon['ScientificName']}"

        taxon_data = {
            "name": taxon['ScientificName'],
            "ncbi.txid": taxon['TaxId'],
            "neuro.role": f"taxon.{taxon['Rank']}",
            "title": tid_title
        }
        if taxon_data:
            lineage_data.append(taxon_data)
    return lineage_data


def filter_neuro_tids(neuro_tids):
    """
    Filter and repair neuro_tids.
    :return: True | False
    """
    filtered_neuro_tids = NeuroTids()
    for neuro_tid in neuro_tids:
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
@click.option("-f", "--overwrite", is_flag=True)
@click.option("-l", "--local", default="")
@click.option("-i", "--integrate", is_flag=True)
@pass_environment
def cli(ctx, taxon_name, overwrite, local, integrate):
    """
    Command `neuro taxon <taxon_name>`.
    By running this command taxon-specific web scraping is performed
    to gather data from NCBI Taxonomy, WikiData, iNaturalist and GBIF. Besides the requested
    taxon, its full taxon chain is added to the NeuroWiki.

    :Example:
    $ neuro taxon Carlito syrichta

    :param ctx:
    :param overwrite:
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
        return

    spinner = halo.Halo(text="Gathering taxon data...", spinner="dots")
    spinner.start()
    taxon_name = " ".join(taxon_name).strip()
    ncbi_lineage = ncbi.get_ncbi_lineage(taxon_name)
    if not ncbi_lineage:
        spinner.stop_and_persist(symbol=style.FAIL, text=f"{taxon_name}: NCBI Taxonomy data")
        return
    else:
        lineage_data = process_ncbi_lineage(ncbi_lineage)
        spinner.stop_and_persist(symbol=style.SUCCESS, text=f"{taxon_name}: NCBI Taxonomy data")

    # Create lineage NeuroTids
    neuro_tids = NeuroTids()
    for taxon_data in lineage_data:
        try:
            neuro_tid = tw_get.neuro_tid(taxon_data["title"])
        except exceptions.TiddlerDoesNotExist:
            neuro_tid = NeuroTid(taxon_data["title"])
        neuro_tid.add_fields(taxon_data)
        neuro_tids.append(neuro_tid)
    neuro_tids = filter_neuro_tids(neuro_tids)
    neuro_tids.chain()
    changes = False

    # Add missing taxons to NeuroWiki
    for neuro_tid in neuro_tids:
        if overwrite or not tw_get.is_tiddler(neuro_tid.title):
            if overwrite:
                DictUtils.represent(neuro_tid.fields)
            if components.bool_prompt(f"Put tiddler \"{neuro_tid.title}\"?"):
                tw_put.neuro_tid(neuro_tid)
                changes = True

    # Establish local filesystem architecture
    current_path = local
    added = False
    for neuro_tid in neuro_tids:
        if neuro_tid.fields["neuro.role"] in OBLIGATORY_TAXA:
            name = neuro_tid.title.split(" ", 1)[1].replace(" ", "_")
            current_path = f"{current_path}/{name}"
            subpath = current_path.replace(f"{local}/", "")
            if "local" in neuro_tid.fields:
                local_path = neuro_tid.fields["local"].replace("file://", "")
                if os.path.isdir(local_path):
                    current_path = local_path
                continue

            if not os.path.isdir(current_path):
                if components.bool_prompt(f"Establish subpath \"{subpath}\"?"):
                    os.mkdir(current_path)
                    neuro_tid.fields["local"] = f"file://{current_path}"
                    tw_put.neuro_tid(neuro_tid)
                else:
                    break
            else:
                if "local" not in neuro_tid.fields:
                    neuro_tid.fields["local"] = f"file://{current_path}"
                    tw_put.neuro_tid(neuro_tid)
                    added = True

    if not changes:
        print("No additions to NeuroWiki.")
    if not added:
        print("No additions to local file system.")
