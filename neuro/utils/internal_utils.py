"""
Internal utility functions.
"""

import logging
from pathlib import Path
import os

import psutil

from neuro.utils import exceptions


BASE_PATHS = {
    "app": "APP",
    "archive": "ARCHIVE",
    "design": "DESIGN",
    "desktop": "DESKTOP",
    "logs": "LOGS",
    "neuro": "NEURO",
    "nf": "NF_DIR",
    "resources": "RESOURCES",
    "storage": "STORAGE",
    "tw5": "TW5",
}

DERIVED_PATHS = {
    "plugins": ("tw5", "plugins"),
    "templates": ("resources", "templates"),
    "tests": ("neuro", "tests"),
    "themes": ("tw5", "themes"),
    "tiddlers": ("storage", "tiddlers"),
    "tiddlywiki.js": ("tw5", "tiddlywiki.js"),
    "wd_queries": ("resources", "queries"),
}


def get_path(keyword, create_if_missing=False):
    """
    Get path for a keyword.
    :param create_if_missing:
    :param keyword: string
    :return:
    """

    if keyword in BASE_PATHS:
        path = Path(os.environ[BASE_PATHS[keyword]])
    elif keyword in DERIVED_PATHS:
        base, *parts = DERIVED_PATHS[keyword]
        path = get_path(base) / Path(*parts)
    else:
        raise exceptions.InternalError(f"Keyword '{keyword}' is not supported.")

    if not path.exists() and not create_if_missing:
        raise exceptions.InvalidPath(f"Path '{path}' for keyword '{keyword}' does not exist in {Path.cwd()}.")
    elif not path.exists() and create_if_missing:
        path.mkdir(parents=True, exist_ok=True)
    else:
        path = path.resolve()

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
