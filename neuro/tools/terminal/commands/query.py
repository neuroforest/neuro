"""
Query NeuroBase
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.base.api import NeuroBase


@click.command("", short_help="")
@click.option("-c", "--cypher", is_flag=True, default=True)
@click.argument("query", required=False)
@pass_environment
def cli(ctx, cypher, query):
    if cypher:
        nb = NeuroBase()
        data = nb.get_data(query)
        print(data)
