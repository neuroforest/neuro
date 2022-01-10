import click

from neuro.tools.terminal.cli import pass_environment


@click.command("taxon", short_help="Organism.")
@click.argument("scientific_name", required=False, nargs=-1)
@pass_environment
def cli(ctx, scientific_name):
	print("The taxon given is: " + " ".join(scientific_name))