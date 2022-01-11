"""
Test the Python module neuro.
"""

import os

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils


@click.command("test", short_help="Test the neuro module.")
@click.argument("path", required=False, type=click.Path(resolve_path=True))
@pass_environment
def cli(ctx, path):
    # Set test path
    if not path:
        path = internal_utils.get_path("tests")

    # Set working directory
    neuro_path = internal_utils.get_path("neuro")
    if os.getcwd() != neuro_path:
        os.chdir(neuro_path)
        print(neuro_path)

    os.system(f"pytest {path}")
