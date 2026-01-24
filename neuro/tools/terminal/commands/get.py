"""
API GET command-line interface.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.tw5api import tw_get


def get_tiddler(tid_title):
    """
    Returns tiddler fields if found.
    :param tid_title:
    """
    fields = tw_get.fields(tid_title)

    if fields:
        fields["title"] = tid_title
        return fields
    else:
        return False


@click.command("get", short_help="NeuroAPI GET method")
@click.argument("resource", required=True)
@pass_environment
def cli(ctx, resource):
    fields = get_tiddler(resource)
    ctx.log(fields)
