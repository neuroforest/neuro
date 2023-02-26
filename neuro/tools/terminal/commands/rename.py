"""
Invoke NeuroForest wiki function $tw.wiki.nfRename.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_actions


@click.command("rename", short_help="rename tiddler")
@click.argument("old_title", required=True)
@click.argument("new_title", required=True)
@pass_environment
def cli(ctx, old_title, new_title):
    tw_actions.rename_tiddler(old_title, new_title)
