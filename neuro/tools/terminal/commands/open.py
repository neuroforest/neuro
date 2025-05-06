"""
Open a tiddler in NeuroWiki.
"""

import time
import subprocess

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_actions, tw_get


@click.command("open", short_help="open a tiddler")
@click.argument("title", required=True)
@pass_environment
def cli(ctx, title):
    response = tw_actions.open_tiddler(title)
    if response.status_code == 204:
        tiddler = tw_get.tiddler(title)
        if "local" in tiddler:
            subprocess.run(["xdg-open", tiddler["local"]])
            time.sleep(0.1)
        subprocess.run(["wmctrl", "-a", "NeuroWiki — taking language to the next level"])
