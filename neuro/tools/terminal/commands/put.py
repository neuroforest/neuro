"""
API PUT command-line interface.
"""

import json

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_put


@click.command("put", short_help="NeuroForest API PUT command.")
@click.argument("tiddler", required=False)
@pass_environment
def cli(ctx, tiddler):
	tw_put.tiddler(json.loads(tiddler))
