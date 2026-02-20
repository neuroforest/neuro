"""
Archive tiddlers.
"""
import json
import os
import sys

import click
from rich.console import Console

from neuro.base import NeuroBase
from neuro.core import Dir, File, Moment
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.terminal.commands import qa, local
from neuro.tools import migrate
from neuro.utils import internal_utils, terminal_style, terminal_components, time_utils


def archive():
    """
    Archive tiddlers.
    """
    with Console().status("Archiving...", spinner="dots"):
        moment_prog = time_utils.MOMENT_4
        month_prog = time_utils.MONTH

        archive_path = internal_utils.get_path('archive', create_if_missing=True) / "json" / month_prog
        os.makedirs(archive_path, exist_ok=True)
        json_path = f"{archive_path}/{moment_prog}.json"

        migrate.migrate_neo4j_to_json(json_path)
        print(f"{terminal_style.SUCCESS} Wiki archived")


def archive_ontology():
    query = """
    MATCH (o)-[r]->(t)
    WHERE o:OntologyNode OR o:OntologyProperty OR o:OntologyRelationship
    RETURN o, r, t;   
    """
    data = NeuroBase().get_data(query)
    ontology_archive_path = (internal_utils.get_path('archive', create_if_missing=True)
                             / "ontology" / f"{time_utils.MOMENT_4}.json")
    with open(ontology_archive_path, "w+") as f:
        json.dump(data, f)

    print(f"{terminal_style.SUCCESS} Ontology archived")


def print_time_from_last_archive():
    tiddler_archive_path = internal_utils.get_path("archive", create_if_missing=True) / "json"
    month_path = max(Dir(tiddler_archive_path).get_children())
    timestamp_path = max(Dir(month_path).get_children())
    last_timestamp = File(timestamp_path).ctime
    current_moment = Moment()
    second_passed = current_moment - last_timestamp
    time_string = time_utils.get_time_string(second_passed)
    print(f"Time since last archive: {terminal_style.BOLD}{time_string}{terminal_style.RESET}")


def remove_latest():
    """
    Remove the latest archive.
    """
    archive_path = internal_utils.get_path('archive', create_if_missing=True) / "json"
    month_path = max(Dir(archive_path).get_children())
    timestamp_path = max(Dir(month_path).get_children())
    if terminal_components.bool_prompt(f"Delete archive entry {timestamp_path.replace(str(archive_path) + '/', '')}?"):
        os.remove(timestamp_path)
        print(f"{terminal_style.SUCCESS} Removed")


@click.command("archive", short_help="archive tiddlers")
@click.option("-c", "--check", is_flag=True)
@click.option("-o", "--ontology", is_flag=True)
@click.option("-r", "--remove", is_flag=True)
@pass_environment
def cli(ctx, check, remove, ontology):
    if check:
        print_time_from_last_archive()
        sys.exit()
    if remove:
        remove_latest()
        sys.exit()
    if ontology:
        archive_ontology()
        sys.exit()
    quality_secured = qa.cli(["--interactive"], standalone_mode=False)
    local_integration_secured = local.cli(["--quality"], standalone_mode=False)
    if all([quality_secured, local_integration_secured]):
        print("-"*50)
        print_time_from_last_archive()
        archive()
