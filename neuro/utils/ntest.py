import os
import subprocess
import sys

import click
import dotenv
import pytest

from neuro.utils import internal_utils


@click.command("ntest", short_help="test Python package neuro",
               context_settings=dict(ignore_unknown_options=True))
@click.argument("mode",
                type=click.Choice(["p", "production", "l", "local", "r", "ruff"]),
                default="l", required=True)
@click.argument("command_args", nargs=-1)
def cli(mode, command_args):
    neuro_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    os.chdir(neuro_path)
    dotenv.load_dotenv(os.path.abspath(".env.defaults"))
    dotenv.load_dotenv(os.path.abspath(".env.testing"), override=True)
    os.environ["ENVIRONMENT"] = "TESTING"

    if mode in ["p", "production"]:
        subprocess.run(["git", "submodule", "update", "--init", "--force"])
        subprocess.run(["git", "submodule", "update", "--remote"])
        subprocess.run(["git", "submodule", "foreach", "git", "checkout", "-f", "origin/master"])
        subprocess.run(["git", "submodule", "foreach", "git", "clean", "-fd"])
        subprocess.run(["rm", "-rf", "venv"])
        subprocess.run(["python3", "-m", "venv", "venv"])
        subprocess.run(["venv/bin/pip", "install", f"git+file://{neuro_path}"])
        subprocess.run(["mkdir", "venv/neuro"])
        subprocess.run("git archive HEAD | tar -x -C venv/neuro", shell=True, check=True)
        if not command_args:
            command_args = ("venv/neuro/tests",)
        pytest.main([*command_args])
        subprocess.run([
            f"{sys.prefix}/bin/ruff",
            "check",
            "--no-respect-gitignore",
            "venv/neuro"
        ])
    elif mode in ["r", "ruff"]:
        subprocess.run([
            f"{sys.prefix}/bin/ruff",
            "check",
            *command_args
        ])
    else:  # mode in ["l", "local"]
        internal_utils.copy_plugins_and_themes()
        tw5_src = internal_utils.get_path("tw5")
        subprocess.run(["rsync", "-a", "--exclude=tw5/.git", tw5_src, neuro_path, "--delete"])
        if not command_args:
            command_args = (internal_utils.get_path("tests"),)
        pytest.main([*command_args])


if __name__ == "__main__":
    cli()
