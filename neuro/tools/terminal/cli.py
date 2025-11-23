"""
Command-line interface. It is available through the command `neuro`.
"""

import os
import sys
import importlib.metadata

import click

from neuro.tools.terminal import style


CONTEXT_SETTINGS = dict(auto_envvar_prefix="NEURO")


class Environment:
    def __init__(self):
        self.verbose = False
        self.home = os.getcwd()

    @staticmethod
    def log(msg, *args):
        """Logs a message to stderr."""
        if args:
            msg %= args
        click.echo(msg, file=sys.stderr)

    def vlog(self, msg, *args):
        """Logs a message to stderr only if verbose is enabled."""
        if self.verbose:
            self.log(msg, *args)


pass_environment = click.make_pass_decorator(Environment, ensure=True)
cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "commands"))


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-v", "--verbose", is_flag=True, help="Enables verbose mode.")
@click.version_option(importlib.metadata.version("neuro"))
@pass_environment
def cli(ctx, verbose):
    """NeuroForest command line interface."""
    ctx.verbose = verbose


def load_commands(cli_group):
    """
    Scans the 'commands' directory and dynamically loads and adds them
    to the click.Group.
    """
    for filename in os.listdir(cmd_folder):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        name = filename[:-3]
        try:
            mod = importlib.import_module(f"neuro.tools.terminal.commands.{name}")
        except Exception as e:
            print(f"{style.RED}ERROR:neuro {name}:{e}{style.RESET}")
            continue

        if hasattr(mod, "cli"):
            cli_group.add_command(mod.cli, name=name)


if os.path.exists(cmd_folder):
    load_commands(cli)
