"""
Query NeuroBase
"""

import click

from neuro.base import NeuroBase
from neuro.tools.terminal.cli import pass_environment


@click.command("", short_help="query NeuroBase")
@click.argument("query", required=True)
@pass_environment
def cli(ctx, query):
    with NeuroBase() as nb:
        data = nb.get_data(query)
    print(data)
