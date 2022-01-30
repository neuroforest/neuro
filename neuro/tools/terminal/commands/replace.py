"""
Invoke NeuroForest wiki function $tw.wiki.nfReplace.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_actions


@click.command("replace", short_help="")
@click.argument("old_text", required=True)
@click.argument("new_text", required=True)
@click.argument("tw_filter", default="")
@pass_environment
def cli(ctx, old_text, new_text, tw_filter):
    tw_actions.replace_text(old_text, new_text, tw_filter)