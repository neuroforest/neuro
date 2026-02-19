"""
NeuroDesktop command-line interface.
"""

import os
import runpy
import sys

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils


def run_desktop_script(script_name, *args):
    script_path = internal_utils.get_path("desktop") / "scripts" / f"{script_name}.py"

    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"NeuroDesktop Script not found: {script_name}")

    # Backup current sys.argv
    old_argv = sys.argv
    try:
        sys.argv = [script_path, *args]
        runpy.run_path(script_path, run_name="__main__")
    finally:
        # Restore original argv
        sys.argv = old_argv


@click.command("desk", short_help="NeuroDesktop")
@click.argument("action", required=True)
@click.argument("args", nargs=-1)
@pass_environment
def cli(ctx, action, args):
    run_desktop_script(action, *args)
