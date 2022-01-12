"""
Test the Python module neuro.
"""

import os

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils


@click.command("test", short_help="Test the neuro module.")
@click.argument("path", required=False, type=click.Path(resolve_path=True))
@click.option("-i", "--integration", is_flag=True)
@click.option("-a", "--full", is_flag=True)
@pass_environment
def cli(ctx, path, integration, full):
    # Set test path
    if not path:
        path = internal_utils.get_path("tests")

    # Set working directory
    neuro_path = internal_utils.get_path("neuro")
    if os.getcwd() != neuro_path:
        os.chdir(neuro_path)
    if integration:
        command = f"pytest -m \"integration\" {path}"
    elif full:
        command = f"pytest {path}"
    else:
        command = f"pytest -m \"not integration\" {path}"
    os.system(command)
