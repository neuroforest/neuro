"""
Replace text in NeuroWiki.
"""
import os

import click

from neuro.tools.local import refactor
from neuro.utils import internal_utils

from neuro.tools.terminal import common
from neuro.tools.terminal.cli import pass_environment


@click.command("replace", short_help="search and replace text")
@click.argument("old_text", required=True)
@click.argument("new_text", required=True)
@click.argument("tw_filter", default="")
@click.option("-l", "--local", is_flag=True)
@pass_environment
def cli(ctx, old_text, new_text, tw_filter, local):
    if local:
        tiddler_path = internal_utils.get_path("tiddlers")
        refactor.update_tiddlers(old_text, new_text, tiddler_path)
        os.system("neuro desk build")
    else:
        common.replace_text(old_text, new_text, tw_filter)
