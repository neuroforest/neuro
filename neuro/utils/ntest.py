"""
Test the Python module neuro.

This module is used for running tests locally. When pushing code to GitHub, the file
.github/workflows/ci.yml is used for automated testing.
"""
import dotenv
import logging
import os
import sys
import subprocess

import click
import pytest

from neuro.utils import internal_utils


@click.command("ntest", short_help="test Python package neuro")
@click.argument("path", required=False, type=click.Path(resolve_path=True))
@click.option("-i", "--integration", is_flag=True)
@click.option("-l", "--local", is_flag=True)
@click.option("-n", "--notintegration", is_flag=True)
@click.option("-p", "--production", is_flag=True)
@click.argument("file", nargs=-1)
def cli(path, integration, notintegration, local, file, production):
    neuro_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    os.chdir(neuro_path)
    dotenv.load_dotenv(os.path.abspath(".env.defaults"))
    dotenv.load_dotenv(os.path.abspath(".env.testing"), override=True)
    os.environ["ENVIRONMENT"] = "TESTING"

    if local and production:
        logging.getLogger(__name__).error("Incompatible options")
        sys.exit()

    # Set test path
    if not path:
        path = internal_utils.get_path("tests")

    # Get tw5 submodule from local file system or from remote repository
    if local:
        internal_utils.copy_plugins_and_themes()
        tw5_src = internal_utils.get_path("tw5")
        subprocess.run(["rsync", "-a", "--exclude=tw5/.git", tw5_src, neuro_path, "--delete"])
    else:
        subprocess.run(["git", "submodule", "update", "--init", "--force"])
        subprocess.run(["git", "submodule", "update", "--remote"])
        subprocess.run(["git", "submodule", "foreach", "git", "checkout", "-f", "origin/master"])
        subprocess.run(["git", "submodule", "foreach", "git", "clean", "-fd"])

    if file:
        path = file

    if production:
        subprocess.run(["rm", "-rf", "venv"])
        subprocess.run(["python3", "-m", "venv", "venv"])
        subprocess.run(["venv/bin/pip", "install", f"git+file://{neuro_path}"])
        subprocess.run("git archive HEAD tests | tar -x -C venv/", shell=True, check=True)
        subprocess.run(["venv/bin/pytest", "venv/tests"])
    elif integration:
        pytest.main(["-v", "-m", "integration", path])
    elif notintegration:
        pytest.main(["-v", "-m", "non integration", path])
    else:
        pytest.main([path])


if __name__ == "__main__":
    cli()
