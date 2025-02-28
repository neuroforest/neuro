"""
NeuroDesktop command-line interface.
"""

import json
import logging
import os
import shutil
import subprocess

import click

from neuro.tools.terminal.cli import pass_environment
from neuro.utils import internal_utils, config


config.load_env_files()


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
    rebld_path = internal_utils.get_path("desktop") + "/rebld.sh"
    subprocess.Popen(rebld_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logging.debug("NeuroDesktop build completed.")


def run():
    null = open(os.devnull, "w", encoding="utf-8")
    subprocess.Popen(internal_utils.get_path("nw"), stdout=null, stderr=null)


def copy_plugins_and_themes():
    for plugin in json.loads(os.getenv("EXTERNAL_PLUGINS")):
        plugin_source_path = plugin["path"]
        plugin_target_path = internal_utils.get_path("plugins") + "/" + plugin["name"]
        shutil.rmtree(plugin_target_path, ignore_errors=True)
        shutil.copytree(plugin_source_path, plugin_target_path)

    for theme in json.loads(os.getenv("EXTERNAL_THEMES")):
        theme_source_path = theme["path"]
        theme_target_path = internal_utils.get_path("themes") + "/" + theme["name"]
        shutil.rmtree(theme_target_path)
        shutil.copytree(theme_source_path, theme_target_path)


def handle_keyword(keyword):
    """
    Handle the keyword that is used by main.js desktop file.
    :param keyword:
    :return:
    """
    file_path = internal_utils.get_path("desktop") + "/args.txt"
    with open(file_path, mode="w+", encoding="utf-8") as f:
        f.write(keyword)


@click.command("desk", short_help="NeuroDesktop")
@click.argument("action", required=True)
@click.argument("keyword", required=False, default="")
@click.option("--core", "-c", is_flag=True)
@click.option("--front", "-f", is_flag=True)
@pass_environment
def cli(ctx, action, keyword, core, front):
    if action == "build":
        copy_plugins_and_themes()
        handle_keyword(keyword)
        build()
    elif action == "close":
        close()
    elif action == "run":
        run()
    else:
        ctx.log(f"Keyword not supported {action}.")
