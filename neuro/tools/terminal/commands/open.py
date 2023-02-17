"""
Open a tiddler in NeuroWiki.
"""

import os

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_actions


@click.command("open", short_help="Open a tiddler in NeuroWiki.")
@click.argument("title", required=True)
@pass_environment
def cli(ctx, title):
    response = tw_actions.open_tiddler(title)
    if response.status_code == 204:
        os.system("wmctrl -a NeuroWiki")
