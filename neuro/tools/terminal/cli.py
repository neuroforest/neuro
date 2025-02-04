"""
Command-line interface. It is available through the command `neuro`.
"""

import os
import sys
import importlib.metadata

import click

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


class NeuroCLI(click.MultiCommand):
    def list_commands(self, ctx):
        rv = []
        for filename in os.listdir(cmd_folder):
            if filename.endswith(".py") and not filename.startswith("_"):
                rv.append(filename[:-3])
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        try:
            mod = __import__(f"neuro.tools.terminal.commands.{name}", None, None, ["cli"])
        except ImportError:
            return
        return mod.cli


@click.command(cls=NeuroCLI, context_settings=CONTEXT_SETTINGS)
@click.option("-v", "--verbose", is_flag=True, help="Enables verbose mode.")
@click.version_option(importlib.metadata.version("neuro"))
@pass_environment
def cli(ctx, verbose):
    """NeuroForest command line interface."""
    ctx.verbose = verbose
