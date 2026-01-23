"""
Helper function and classes used by various tests.
"""

import filecmp
import glob
import hashlib
import io
import logging
import os
import shutil
import subprocess
import sys

from neuro.utils import network_utils


def populate_wf(wf, test_case):
    from neuro.core import TiddlerList
    from neuro.tools.tw5api import tw_put
    tiddler_json = get_test_file(f"input/tiddlers/{test_case}.json")
    tiddler_list = TiddlerList.from_json(tiddler_json)
    tw_put.tiddler_list(tiddler_list, port=wf.port)


def are_dirs_identical(dir1, dir2):
    cmp_object = filecmp.dircmp(dir1, dir2)
    if not cmp_object.diff_files:
        return True
    else:
        return False


def get_path(file_subpath):
    path = f"{os.path.abspath('.')}/{file_subpath}"  # IMPORTANT: must be in dir
    return path


def get_test_file(file_name, exists=True, multi=False):
    """
    Get a test file according to glob file path expansion.
    :param file_name:
    :param exists: does file have to exist
    :param multi:
    :return:
    """
    test_data_dir = os.path.abspath("resources/test")  # IMPORTANT: must be in dir
    if exists:
        file_paths = sorted(glob.glob(f"{test_data_dir}/*{file_name}*"))
        if len(file_paths) == 1:
            return file_paths[0]
        elif not file_paths:
            logging.error(f"Test data file not found: {file_name}")
            logging.error(f"Test data dir: {test_data_dir}")
            raise FileNotFoundError
        else:
            if not multi:
                logging.error(f"Test data file name not specific enough, found {len(file_paths)}")
                raise FileNotFoundError
            else:
                return file_paths
    else:
        return f"{test_data_dir}/{file_name}"


def get_hash(string):
    """
    Get a hash from a string.
    :param string:
    :return:
    """
    m = hashlib.sha1()
    m.update(bytes(string, encoding="utf-8"))
    digest = m.hexdigest()
    return digest


def run_wiki_folder(path, port):
    if network_utils.is_port_in_use(port):
        network_utils.release_port(port)

    process = subprocess.Popen([
        "node",
        "tw5/tiddlywiki.js",
        path,
        "--listen",
        f"port={port}",
        "readers=(anon)",
        "writers=(anon)"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    network_utils.wait_for_socket("127.0.0.1", port)

    return process


def create_and_run_wiki_folder(tiddlers_name, port):
    """
    Create a wiki folder and run it on the specified port.
    :param tiddlers_name: name of the tiddlers folder to use
    :param port:
    :return: process object of the running wiki
    """
    output_wiki_folder_path = get_test_file(f"output/wf-{tiddlers_name}", exists=False)
    os.makedirs(output_wiki_folder_path)
    tiddlywiki_info = get_test_file("input/tiddlywiki.info")
    shutil.copy(tiddlywiki_info, output_wiki_folder_path)
    try:
        tiddlers_folder = get_test_file(f"input/tiddlers/{tiddlers_name}")
        shutil.copytree(tiddlers_folder, f"{output_wiki_folder_path}/tiddlers")
    except FileNotFoundError:
        pass

    process = run_wiki_folder(output_wiki_folder_path, port)

    return process


class Capturing(list):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = io.StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio    # free up some memory
        sys.stdout = self._stdout
