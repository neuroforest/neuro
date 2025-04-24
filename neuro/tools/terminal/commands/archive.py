"""
Archive tiddlers.
"""

import shutil
import sys

import click
from rich.console import Console
from sympy.integrals.heurisch import components

from neuro.tools.terminal import style, components
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.terminal.commands import qa, local
from neuro.utils import internal_utils, time_utils
from neuro.core.deep import Dir, Moment


def archive():
    """
    Archive tiddlers.
    """
    with Console().status("Archiving...", spinner="dots"):
        moment_prog = time_utils.MOMENT
        month_prog = time_utils.MONTH

        tiddlers_path = internal_utils.get_path("tiddlers")
        archive_path = f"{internal_utils.get_path('archive')}/tiddlers/{month_prog}/{moment_prog}"

        shutil.copytree(tiddlers_path, archive_path, dirs_exist_ok=False)
        print(f"{style.SUCCESS} Wiki archived")


def print_time_from_last_archive():
    tiddler_archive_path = internal_utils.get_path("archive") + "/tiddlers/"
    month_path = max(Dir(tiddler_archive_path).get_children())
    timestamp_path = max(Dir(month_path).get_children())
    last_timestamp = Dir(timestamp_path).ctime
    current_moment = Moment(form="now")
    second_passed = current_moment - last_timestamp
    time_string = time_utils.get_time_string(second_passed)
    print(f"Time since last archive: {style.BOLD}{time_string}{style.RESET}")


def remove_latest():
    """
    Remove the latest archive.
    """
    archive_path = f"{internal_utils.get_path('archive')}/tiddlers/"
    month_path = max(Dir(archive_path).get_children())
    timestamp_path = max(Dir(month_path).get_children())
    if components.bool_prompt(f"Delete archive entry {timestamp_path.replace(archive_path, '')}?"):
        shutil.rmtree(timestamp_path, ignore_errors=True)
        print(f"{style.SUCCESS} Removed")


@click.command("archive", short_help="archive tiddlers")
@click.option("-c", "--check", is_flag=True)
@click.option("-r", "--remove", is_flag=True)
@pass_environment
def cli(ctx, check, remove):
    if check:
        print_time_from_last_archive()
        sys.exit()
    if remove:
        remove_latest()
        sys.exit()
    quality_secured = qa.cli(["--interactive"], standalone_mode=False)
    local_integration_secured = local.cli(["--quality"], standalone_mode=False)
    if all([quality_secured, local_integration_secured]):
        print("-"*50)
        print_time_from_last_archive()
        archive()
