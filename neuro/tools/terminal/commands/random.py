"""
Open a random tiddler in NeuroWiki.
"""

import random as py_random

import click
import halo

from neuro.tools.api import tw_get

from neuro.tools.terminal import style
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.terminal.commands import open


@click.command("random", short_help="Open a tiddler in NeuroWiki.")
@pass_environment
def cli(ctx):
    spinner = halo.Halo(text="Searching NeuroWiki...", spinner="dots")
    spinner.start()
    tid_titles = tw_get.tw_fields(["title"], "[all[]]")
    tid_title = py_random.choice(tid_titles)["title"]
    spinner.stop()
    print(f"Random tiddler ➜ {style.YELLOW}{style.BOLD}{tid_title}{style.RESET}")
    open.cli([tid_title])
