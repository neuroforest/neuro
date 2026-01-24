"""
Open a tiddler in NeuroWiki.
"""

import time
import subprocess

import click

from neuro.core.data.str import Uuid
from neuro.tools.terminal.cli import pass_environment
from neuro.tools.tw5api import tw_actions, tw_get


@click.command("open", short_help="open a tiddler")
@click.argument("title", required=True)
@pass_environment
def cli(ctx, title):
    if Uuid.is_valid_uuid_v4(title):
        try:
            title = tw_get.filter_output(f"[search:neuro.id[{title}]]")[0]
        except IndexError:
            print(f"Not found: {title}")
            return
    response = tw_actions.open_tiddler(title)
    if response.status_code == 204:
        fields = tw_get.fields(title)
        if "local" in fields:
            subprocess.run(["xdg-open", fields["local"]])
            time.sleep(0.1)
