"""
Command `neuro taxon <taxon_name>`, where the argument taxon_name is
the scientific name of the taxon.
"""

import os

import click
from rich.console import Console

from neuro.core.tid import TiddlerList, Tiddler
from neuro.tools.tw5api import tw_get, tw_put
from neuro.tools.science import biology
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.integrations import wikidata, ncbi
from neuro.utils import exceptions, internal_utils, terminal_components, terminal_style


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


def filter_tiddler_list(tiddler_list: TiddlerList, port):
    """
    Filter and repair tiddler list.
    :return: True | False
    """
    filtered = TiddlerList()
    for tiddler in tiddler_list:
        tid_title = tiddler.title
        if tiddler.fields["neuro.role"] in OBLIGATORY_TAXA:
            filtered.append(tiddler)
        else:
            if tw_get.is_tiddler(tid_title, port=port):
                fields = tw_get.fields(tid_title, port=port)
                tiddler.add_fields(fields, overwrite=False)
                filtered.append(tiddler)
    return filtered


def add_translations(tiddler):
    ncbi_taxon_id = tiddler.fields["ncbi.txid"]
    query_file_path = internal_utils.get_path("wd_queries") / "taxon.rq"
    wd_res = wikidata.fetch(query_file_path, {"ncbi-taxon-id": ncbi_taxon_id})
    if len(wd_res) > 1:
        print("Warning: multiple results for WikiData query")
        return tiddler
    elif not wd_res:
        print(f"Warning: No WikiData available for {tiddler.fields['name']}")
        return tiddler
    else:
        wd_res = wd_res[0]

    if "labelSL" in wd_res:
        label_sl = wd_res["labelSL"]["value"]
        if label_sl != tiddler.fields["name"]:
            tiddler.fields["trans.slv"] = label_sl.lower()

    if "labelEN" in wd_res:
        label_en = wd_res["labelEN"]["value"]
        if label_en != tiddler.fields["name"]:
            tiddler.fields["trans.eng"] = label_en

    return tiddler


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
        taxon_id = terminal_components.selector(id_list, metadata)
        if not taxon_id:
            return

    with Console().status("Gathering taxon data...", spinner="dots"):
        ncbi_lineage = ncbi.get_lineage(taxon_id)
        if not ncbi_lineage:
            print(f"{terminal_style.FAIL} {taxon_name}: NCBI bad request, try again")
            return
        else:
            lineage_data = process_ncbi_lineage(ncbi_lineage, port=port)
            print(f"{terminal_style.SUCCESS} {lineage_data[-1]['name']}: NCBI Taxonomy data")

    # Create lineage TiddlerList
    tiddler_list = TiddlerList()
    for taxon_data in lineage_data:
        try:
            tiddler = tw_get.tiddler(taxon_data["title"], port=port)
        except exceptions.TiddlerDoesNotExist:
            tiddler = Tiddler(taxon_data["title"])
        tiddler.add_fields(taxon_data)
        tiddler_list.append(tiddler)
    tiddler_list = filter_tiddler_list(tiddler_list, port)
    tiddler_list.chain()

    # Add missing taxa to NeuroWiki
    changes = False
    for tiddler in tiddler_list:
        if overwrite and yes:
            tw_put.tiddler(tiddler, port=port)
            changes = True
        elif yes and not tw_get.is_tiddler(tiddler.title, port=port):
            tw_put.tiddler(tiddler, port=port)
            changes = True
        elif overwrite or not tw_get.is_tiddler(tiddler.title, port=port):
            tiddler = add_translations(tiddler)
            if terminal_components.bool_prompt(f"Put tiddler \"{tiddler.title}\"?"):
                tw_put.tiddler(tiddler, port=port)
                changes = True

    # Establish local filesystem architecture
    if yes:
        return
    current_path = local
    added = False
    for tiddler in tiddler_list:
        if tiddler.fields["neuro.role"] in OBLIGATORY_TAXA:
            name = tiddler.title.split(" ", 1)[1].replace(" ", "_")
            current_path = f"{current_path}/{name}"
            subpath = current_path.replace(f"{local}/", "")
            if "local" in tiddler.fields:
                local_path = tiddler.fields["local"].replace("file://", "")
                if os.path.isdir(local_path):
                    current_path = local_path
                continue

            if not os.path.isdir(current_path):
                if terminal_components.bool_prompt(f"Establish subpath \"{subpath}\"?"):
                    os.mkdir(current_path)
                    tiddler.fields["local"] = f"file://{current_path}"
                    tw_put.tiddler(tiddler, port=port)
                else:
                    break
            else:
                if "local" not in tiddler.fields:
                    tiddler.fields["local"] = f"file://{current_path}"
                    tw_put.tiddler(tiddler, port=port)
                    added = True

    if not changes:
        print("No additions to NeuroWiki.")
    if not added:
        print("No additions to local file system.")
