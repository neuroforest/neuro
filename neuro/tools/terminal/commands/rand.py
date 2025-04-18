"""
Open a random tiddler in NeuroWiki.
"""

import random as py_random

import click
from rich.console import Console

from neuro.tools.api import tw_get

from neuro.tools.terminal import style, components
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.terminal.commands import open


@click.command("random", short_help="open a random tiddler")
@click.option("-s", "--safe", is_flag=True)
@pass_environment
def cli(ctx, safe):
    spinner = Console().status("Searching NeuroWiki...", spinner="dots")
    spinner.start()
    tid_titles = tw_get.tw_fields(["title"], "[all[]]")
    tid_title = py_random.choice(tid_titles)["title"]
    spinner.stop()
    print(f"Random tiddler:  {style.YELLOW}{style.BOLD}{tid_title}{style.RESET}")
    if safe:
        input("")
        open.cli([tid_title])
    else:
        open.cli([tid_title])
