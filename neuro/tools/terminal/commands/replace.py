"""
Replace text in NeuroWiki.
"""

import click

from neuro.tools.terminal.cli import pass_environment


@click.command("replace", short_help="search and replace text")
@click.argument("old_text", required=True)
@click.argument("new_text", required=True)
@click.argument("tw_filter", default="")
@click.option("-l", "--local", is_flag=True)
@pass_environment
def cli(ctx, old_text, new_text, tw_filter, local):
    raise NotImplementedError
