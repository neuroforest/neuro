"""
Invoke NeuroForest wiki function $tw.wiki.nfMerge.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.tw5api import tw_actions


@click.command("merge", short_help="merge tiddlers")
@click.argument("titles", required=True, nargs=-1)
@pass_environment
def cli(ctx, titles):
    """
    Merge tiddlers by ascending priority.
    """
    tw_actions.merge_tiddlers(list(titles))
