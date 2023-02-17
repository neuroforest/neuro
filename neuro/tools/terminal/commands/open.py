"""
Open a tiddler in NeuroWiki.
"""

import click
import os

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_actions


@click.command("open", short_help="Open a tiddler in NeuroWiki.")
@click.argument("title", required=True)
@pass_environment
def cli(ctx, title):
    tw_actions.open_tiddler(title)
    os.system("wmctrl -a NeuroWiki")

