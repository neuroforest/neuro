"""
Query NeuroBase
"""

import click

from neuro.base.api import NeuroBase
from neuro.tools.terminal.cli import pass_environment

from neuro.base import nql


@click.command("", short_help="query NeuroBase")
@click.option("-c", "--cypher", is_flag=True, default=False)
@click.option("-n", "--nql-query", is_flag=True, default=False)
@click.argument("query", required=False)
@pass_environment
def cli(ctx, cypher, nql_query, query):
    if cypher:
        nb = NeuroBase()
        data = nb.get_data(query)
        print(data)
    elif nql_query:
        nql.session()
    else:
        print("Nothing to do")
