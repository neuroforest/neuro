"""
Search NeuroForest command-line interface.
"""

import json

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_actions


@click.command("search", short_help="search wiki")
@click.argument("query", required=False)
@pass_environment
def cli(ctx, query):
    tw_actions.search(query)
