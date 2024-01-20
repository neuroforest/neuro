"""
Archive tiddlers.
"""

import shutil

import click
import halo

from neuro.tools.terminal import components
from neuro.tools.terminal import style
from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils, time_utils


def archive():
    """Archive tiddlers."""
    # Display spinner
    spinner = halo.Halo(text="Archiving...", spinner="dots")
    spinner.start()

    moment_prog = time_utils.MOMENT
    month_prog = time_utils.MONTH

    tiddlers_path = internal_utils.get_path("tiddlers")
    archive_path = internal_utils.get_path("archive") + "/tiddlers/" + month_prog + "/" + moment_prog

    try:
        shutil.copytree(tiddlers_path, archive_path, dirs_exist_ok=False)
        spinner.stop_and_persist(symbol=style.SUCCESS, text="Wiki archived")
    except FileExistsError:
        spinner.stop_and_persist(symbol=style.FAIL)
        if components.bool_prompt("Already archived today. Overwrite?"):
            spinner.start()
            shutil.copytree(tiddlers_path, archive_path, dirs_exist_ok=True)
            spinner.stop_and_persist(symbol=style.SUCCESS, text="Wiki archived")


@click.command("archive", short_help="archive tiddlers")
@pass_environment
def cli(ctx):
    archive()
