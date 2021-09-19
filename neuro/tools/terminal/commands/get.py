"""
API GET command-line interface.
"""

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.tools.api import tw_get


def get_tiddler(tid_title, **kwargs):
	"""
	Obtains and returns tiddler if it can be done.
	:param tid_title:
	:param kwargs:
	:return: tiddler
	"""
	tid_tags = kwargs.get("tags", False)
	tiddler = tw_get.tiddler(tid_title, **kwargs)

	if tiddler:
		tiddler["title"] = tid_title
		if tid_tags:
			tiddler["tags"] = tid_tags

		return tiddler
	else:
		return False


@click.command("get", short_help="NeuroForest API GET command.")
@click.argument("resource", required=True)
@pass_environment
def cli(ctx, resource):
	tiddler = get_tiddler(resource)
	ctx.log(tiddler)
