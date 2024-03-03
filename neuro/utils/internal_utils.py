"""
Internal utility constants and functions.
"""

import logging
import os
import sys

import psutil

from neuro.utils import SETTINGS, exceptions


def get_path(keyword):
    """
    Get path for a keyword.
    :param keyword: string
    :return:
    """
    keyword_index = {
        "archive": f"{SETTINGS.STORAGE}/archive",
        "desktop": SETTINGS.DESKTOP,
        "neuro": SETTINGS.NEURO,
        "nw": f"{SETTINGS.DESKTOP}/output/linux64/TiddlyDesktop-linux64-v0.0.14/nw",
        "plugins": f"{SETTINGS.TW5}/plugins",
        "resources": f"{SETTINGS.NEURO}/resources",
        "templates": f"{SETTINGS.NEURO}/resources/templates",
        "tests": f"{SETTINGS.NEURO}/tests",
        "themes": f"{SETTINGS.TW5}/themes",
        "tiddlers": f"{SETTINGS.STORAGE}/tiddlers",
        "tw5": SETTINGS.TW5,
        "wd_queries": f"{SETTINGS.NEURO}/resources/queries"
    }

    if keyword not in keyword_index:
        exceptions.InternalError(f"Keyword '{keyword}' is not supported.")
        sys.exit()

    path = keyword_index[keyword]

    if not os.path.exists(path):
        raise exceptions.InvalidPath(f"Path '{path}' for keyword '{keyword}' does not exist.")
        sys.exit

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


def get_tiddler_path(tid_title):
    """
    Return the path to the tid file p
    :param tid_title:
    :return:
    """
    tiddlers_path = get_path("tiddlers")
    tiddler_path = f"{tiddlers_path}/{tid_title}.tid"
    return tiddler_path
