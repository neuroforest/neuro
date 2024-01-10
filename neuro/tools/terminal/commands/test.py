"""
Test the Python module neuro.
"""

import os

import click
import pytest

from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils


@click.command("test", short_help="test Python package neuro")
@click.argument("path", required=False, type=click.Path(resolve_path=True))
@click.option("-a", "--full", is_flag=True)
@click.option("-i", "--integration", is_flag=True)
@click.option("-n", "--notintegration", is_flag=True)
@pass_environment
def cli(ctx, path, full, integration, notintegration):
    # Set test path
    if not path:
        path = internal_utils.get_path("tests")

    # Set working directory
    neuro_path = internal_utils.get_path("neuro")
    if os.getcwd() != neuro_path:
        os.chdir(neuro_path)
    if integration:
        pytest.main(["-m", "integration", path])
    elif notintegration:
        pytest.main(["-m", "non integration", path])
    else:
        pytest.main([path])