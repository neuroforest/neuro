"""
NeuroDesktop command-line interface.
"""

import logging
import os
import subprocess

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils


def close():
	logging.debug("Trying to kill current NeuroDesktop process.")

	process_list = internal_utils.get_process("name", "nw")

	if process_list:
		for process in process_list:
			process.kill()
		logging.debug("Current NeuroDesktop process killed.")
	else:
		logging.debug("NeuroDesktop process not found")


def remove_critical():
	"""
	Remove files critical for updating. Tweaking with source code requires this.
	"""
	core = internal_utils.get_tiddler_path("$__core.json")
	core_meta = internal_utils.get_tiddler_path("$__core.json.meta")
	try:
		os.remove(core)
		os.remove(core_meta)
	except FileNotFoundError:
		pass


def build():
	"""
	Rebuilds the NeuroDesktop instance currently running.
	"""
	close()
	remove_critical()

	logging.debug("Creating new NeuroDesktop.")
	logging.info(internal_utils.NF_DIR)
	rebld_path = internal_utils.NF_DIR + "/desktop/rebld.sh"
	subprocess.Popen(rebld_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	logging.debug("NeuroDesktop build completed.")


def run():
	null = open(os.devnull, "w", encoding="utf-8")
	subprocess.Popen(internal_utils.get_path("nw"), stdout=null, stderr=null)


def handle_args(args):
	file_path = internal_utils.NF_DIR + "/desktop/args.txt"
	with open(file_path, mode="w+", encoding="utf-8") as f:
		f.write(args)


@click.command("desk", short_help="NeuroForest desktop.")
@click.argument("action", required=True)
@click.argument("keyword", required=False)
@pass_environment
def cli(ctx, action, keyword):
	if action == "build":
		if keyword:
			handle_args(keyword)
		build()
	elif action == "close":
		close()
	elif action == "run":
		run()
	else:
		ctx.log(f"Keyword not supported {action}.")