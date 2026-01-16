"""
Open a random tiddler in NeuroWiki.
"""

import random as py_random

import click
from rich.console import Console

from neuro.tools.tw5api import tw_get
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.terminal.commands import open
from neuro.utils import terminal_style


@click.command("random", short_help="open a random tiddler")
@click.option("-s", "--safe", is_flag=True)
@click.option("-j", "--journal", is_flag=True)
@click.option("-q", "--quote", is_flag=True)
@pass_environment
def cli(ctx, safe, journal, quote):
    spinner = Console().status("Searching NeuroWiki...", spinner="dots")
    spinner.start()
    if journal:
        tw_filter = "[tag[JOURNAL]]"
    elif quote:
        tw_filter = "[search:title[ #Quote ]]"
    else:
        tw_filter = "[all[]]"
    tid_titles = tw_get.tw_fields(["title"], tw_filter)
    tid_title = py_random.choice(tid_titles)["title"]
    spinner.stop()
    print(f"Random tiddler:  {terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET}")
    if safe:
        input("")
        open.cli([tid_title])
    else:
        open.cli([tid_title])
