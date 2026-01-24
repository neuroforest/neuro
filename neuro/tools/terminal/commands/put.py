"""
API PUT command-line interface.
"""

import json

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.tw5api import tw_put


@click.command("put", short_help="NeuroAPI PUT method")
@click.argument("fields", required=False)
@pass_environment
def cli(ctx, fields):
    tw_put.fields(json.loads(fields))
