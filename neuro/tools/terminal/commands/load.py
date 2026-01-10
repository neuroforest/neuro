"""
Load an object form NeuroBase into NeuroWiki.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.tw5api import tw_actions


@click.command("load", short_help="load object into NeuroWiki")
@click.argument("title", required=True)
@pass_environment
def cli(ctx, title):
    tw_actions.load(title)
