"""
Command `neuro taxon <taxon_name>`, where the argument taxon_name is
the scientific name of the taxon.
"""

import os

import click
from rich.console import Console

from neuro.core.tid import NeuroTids, NeuroTid
from neuro.tools.api import tw_get, tw_put
from neuro.tools.science import biology
from neuro.tools.terminal import components, style
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.integrations import wikidata, ncbi
from neuro.utils import exceptions, internal_utils


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


def process_ncbi_lineage(ncbi_lineage, port=None):
    port = port or os.getenv("PORT")
    lineage_data = list()
    for taxon in ncbi_lineage:
        prefix = biology.get_prefix(taxon["Rank"], port=port)
        if not prefix:
            tid_title = taxon["ScientificName"]
        else:
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


def filter_neuro_tids(neuro_tids, port):
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
            if tw_get.is_tiddler(tid_title, port=port):
                tiddler = tw_get.tiddler(tid_title, port=port)
                neuro_tid.add_fields(tiddler, overwrite=False)
                filtered_neuro_tids.append(neuro_tid)
    return filtered_neuro_tids


def add_translations(neuro_tid):
    ncbi_taxon_id = neuro_tid.fields["ncbi.txid"]
    query_file_path = os.path.join(internal_utils.get_path("wd_queries"), "taxon.rq")
    wd_res = wikidata.fetch(query_file_path, {"ncbi-taxon-id": ncbi_taxon_id})
    if len(wd_res) > 1:
        print("Warning: multiple results for WikiData query")
        return neuro_tid
    elif not wd_res:
        print(f"Warning: No WikiData available for {neuro_tid.fields['name']}")
        return neuro_tid
    else:
        wd_res = wd_res[0]

    if "labelSL" in wd_res:
        label_sl = wd_res["labelSL"]["value"]
        if label_sl != neuro_tid.fields["name"]:
            neuro_tid.fields["trans.slv"] = label_sl.lower()

    if "labelEN" in wd_res:
        label_en = wd_res["labelEN"]["value"]
        if label_en != neuro_tid.fields["name"]:
            neuro_tid.fields["trans.eng"] = label_en

    return neuro_tid


@click.command("taxon", short_help="import taxon")
@click.argument("taxon_name", required=True)
@click.option("-f", "--overwrite", is_flag=True)
@click.option("-l", "--local", default="")
@click.option("-y", "--yes", is_flag=True)
@click.option("--port", default=os.getenv("PORT"))
@pass_environment
def cli(ctx, taxon_name, overwrite, local, yes, port):
    """
    Command `neuro taxon <taxon_name>`.
    By running this command taxon-specific web scraping is performed
    to gather data from NCBI Taxonomy, WikiData, iNaturalist and GBIF. Besides the requested
    taxon, its full taxon chain is added to the NeuroWiki.

    :Example:
    $ neuro taxon "Carlito syrichta"

    :param ctx:
    :param overwrite:
    :param taxon_name: scientific name of the taxon
    :param local: path to local organism file tree
    :param yes: addition to
    :param port:
    :return:
    """
    if not taxon_name:
        print("Error: no taxon name given")
        return

    # Taxon identification
    id_list = ncbi.resolve_taxon_name(taxon_name)
    if len(id_list) == 0:
        print(f"Error: taxon {taxon_name} not found")
        return
    elif len(id_list) == 1:
        taxon_id = id_list[0]
    else:
        print("Multiple taxa with this name found")
        metadata = [ncbi.get_taxon_info(i)['Division'] for i in id_list]
        taxon_id = components.selector(id_list, metadata)
        if not taxon_id:
            return

    with Console().status("Gathering taxon data...", spinner="dots"):
        ncbi_lineage = ncbi.get_lineage(taxon_id)
        if not ncbi_lineage:
            print(f"{style.FAIL} {taxon_name}: NCBI bad request, try again")
            return
        else:
            lineage_data = process_ncbi_lineage(ncbi_lineage, port=port)
            print(f"{style.SUCCESS} {lineage_data[-1]['name']}: NCBI Taxonomy data")

    # Create lineage NeuroTids
    neuro_tids = NeuroTids()
    for taxon_data in lineage_data:
        try:
            neuro_tid = tw_get.neuro_tid(taxon_data["title"], port=port)
        except exceptions.TiddlerDoesNotExist:
            neuro_tid = NeuroTid(taxon_data["title"])
        neuro_tid.add_fields(taxon_data)
        neuro_tids.append(neuro_tid)
    neuro_tids = filter_neuro_tids(neuro_tids, port)
    neuro_tids.chain()

    # Add missing taxa to NeuroWiki
    changes = False
    for neuro_tid in neuro_tids:
        if overwrite and yes:
            tw_put.neuro_tid(neuro_tid, port=port)
            changes = True
        elif yes and not tw_get.is_tiddler(neuro_tid.title, port=port):
            tw_put.neuro_tid(neuro_tid, port=port)
            changes = True
        elif overwrite or not tw_get.is_tiddler(neuro_tid.title, port=port):
            neuro_tid = add_translations(neuro_tid)
            if components.bool_prompt(f"Put tiddler \"{neuro_tid.title}\"?"):
                tw_put.neuro_tid(neuro_tid, port=port)
                changes = True

    # Establish local filesystem architecture
    if yes:
        return
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
                    tw_put.neuro_tid(neuro_tid, port=port)
                else:
                    break
            else:
                if "local" not in neuro_tid.fields:
                    neuro_tid.fields["local"] = f"file://{current_path}"
                    tw_put.neuro_tid(neuro_tid, port=port)
                    added = True

    if not changes:
        print("No additions to NeuroWiki.")
    if not added:
        print("No additions to local file system.")
