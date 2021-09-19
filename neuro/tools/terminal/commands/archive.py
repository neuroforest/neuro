"""
File archive command-line interface.
"""

import logging
import os
import sys

import click
import halo

from neuro.utils import (
	time_utils,
	internal_utils,
	exceptions)
from neuro.tools.terminal import style
from neuro.tools.terminal.cli import pass_environment


def archive(resource_path, scope):
	scope_archive = scope["archive"]
	scope_path = scope["path"]
	resource_subpath = resource_path.split(scope_path)[1]
	new_resource_path = scope_archive + "/" + time_utils.DATE + resource_subpath
	try:
		os.renames(resource_path, new_resource_path)
	except FileNotFoundError:
		print(f"ERROR: No file {resource_path}")
		sys.exit()


def determine_scope(resource_path):
	# Determine neuro scope.
	divisions = [
		"design",
		"desktop",
		"neuro",
		"tw"
	]

	scope = dict()
	nf = internal_utils.get_path("nf")
	if nf in resource_path:
		for div in divisions:
			div_path = internal_utils.get_path(div)
			if div_path in resource_path:
				scope = {
					"path": div_path,
					"archive": internal_utils.get_path("archive") + "/" + div
				}
				break

	# Check if scope was found.
	if not scope:
		logging.error(f"Scope was not found for resource: {resource_path}")
		raise exceptions.ScopeError()
	else:
		return scope


def get_wiki_archive_path():
	wiki_archive_dir = str(
		internal_utils.NF_DIR
		+ "/storage/archive/wikis/"
		+ time_utils.YEAR
		+ "/"
		+ time_utils.MONTH)

	os.makedirs(wiki_archive_dir, exist_ok=True)

	wiki_archive_path = str(
		wiki_archive_dir
		+ "/"
		+ "wiki"
		+ time_utils.DATE
		+ ".html")

	return wiki_archive_path


@click.command("archive", short_help="Archive.")
@click.argument("path", required=False, type=click.Path(resolve_path=True))
@pass_environment
def cli(ctx, path):
	spinner = halo.Halo(text="Archiving...", spinner="dots")
	spinner.start()
	scope = determine_scope(path)
	archive(path, scope)
	archive_text = f"Archived '{path}'"
	spinner.stop_and_persist(symbol=style.SUCCESS, text=archive_text)
