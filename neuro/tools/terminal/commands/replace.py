"""
Invoke NeuroForest wiki function $tw.wiki.nfReplace.
"""
import os
import sys

import click

from neuro.tools.api import tw_actions
from neuro.tools.local import refactor
from neuro.utils import internal_utils

from neuro.tools.terminal.cli import pass_environment


def check_text(old_text, new_text):
    fail = False
    if any([x for x in old_text if x in "[{|}]"]):
        fail = True
    if any([x for x in new_text if x in "[{|}]"]):
        fail = True

    if fail:
        print("Error: Forbidden character in arguments, avoid [ { | } ] "
              "or use option '-l' | '--local'")
        sys.exit()


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
        check_text(old_text, new_text)
        tw_actions.replace_text(old_text, new_text, tw_filter=tw_filter)
