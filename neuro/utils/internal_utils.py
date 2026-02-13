"""
Internal utility functions.
"""

import contextlib
import json
import logging
import os
import shutil

import psutil

from neuro.utils import exceptions


@contextlib.contextmanager
def chdir(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)

def copy_plugins_and_themes():
    tw5_path = get_path("tw5")
    for plugin in json.loads(os.getenv("EXTERNAL_PLUGINS")):
        plugin_source_path = plugin["path"]
        plugin_target_path = tw5_path + "/plugins/" + plugin["name"]
        shutil.rmtree(plugin_target_path, ignore_errors=True)
        shutil.copytree(plugin_source_path, plugin_target_path)

    for theme in json.loads(os.getenv("EXTERNAL_THEMES")):
        theme_source_path = theme["path"]
        theme_target_path = tw5_path + "/themes/" + theme["name"]
        shutil.rmtree(theme_target_path, ignore_errors=True)
        shutil.copytree(theme_source_path, theme_target_path)


def get_path(keyword):
    """
    Get path for a keyword.
    :param keyword: string
    :return:
    """

    keyword_index = {
        "app": os.getenv("APP"),
        "archive": f"{os.getenv('STORAGE')}/archive",
        "design": os.getenv("DESIGN"),
        "desktop": os.getenv("DESKTOP"),
        "neuro": os.getenv("NEURO"),
        "plugins": f"{os.getenv('TW5')}/plugins",
        "resources": f"{os.getenv('RESOURCES')}",
        "templates": f"{os.getenv('RESOURCES')}/templates",
        "tests": f"{os.getenv('NEURO')}/tests",
        "themes": f"{os.getenv('tw5')}/themes",
        "tiddlers": f"{os.getenv('STORAGE')}/tiddlers",
        "tiddlywiki.js": f"{os.getenv("TW5")}/tiddlywiki.js",
        "tw5": os.getenv("TW5"),
        "wd_queries": f"{os.getenv('RESOURCES')}/queries"
    }

    if keyword not in keyword_index:
        raise exceptions.InternalError(f"Keyword '{keyword}' is not supported.")

    path = keyword_index[keyword]

    if not os.path.exists(path):
        raise exceptions.InvalidPath(f"Path '{path}' for keyword '{keyword}' does not exist in {os.getcwd()}.")
    else:
        path = os.path.abspath(path)

    logging.debug(f"Obtained path {path} for keyword {keyword}")
    return path


def get_process(name, value):
    """

    :param name: process property name
    :param value: process property value
    :return:
    """

    process_list = list()
    process_dict = get_process_dict()
    for process in process_dict.values():
        try:
            if process.__getattribute__(name)() == value:
                process_list.append(process)
        except AttributeError:
            continue

    return process_list


def get_process_dict():
    """
    Get the list of all running processes.
    """
    pids = psutil.pids()
    process_dict = dict()
    for pid in pids:
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue
        process_dict[pid] = process
    return process_dict
