"""
Search NeuroForest command-line interface.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.tw5api import tw_actions, tw_get


@click.command("search", short_help="search wiki")
@click.argument("query", required=False)
@pass_environment
def cli(ctx, query):
    tw_actions.search(query)
    if tw_get.is_tiddler(query):
        tw_actions.open_tiddler(query)
