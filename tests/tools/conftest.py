import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from neuro.core.tid import WikiFolder
from neuro.tools.tw5api import tw_del

from ..helper import get_test_file, get_path, populate_wf


@pytest.fixture(scope="package")
def wf_process():
    """CardsDB object connected to a temporary database"""
    tiddlywiki_info = get_test_file("input/tiddlywiki.info")
    test_port = os.getenv("TEST_PORT")
    with TemporaryDirectory() as temp_wiki_folder:
        shutil.copy(tiddlywiki_info, temp_wiki_folder)
        os.makedirs(Path(temp_wiki_folder) / "tiddlers")
        wiki_folder = WikiFolder(
            temp_wiki_folder,
            port=test_port,
            host="127.0.0.1",
            tw5=get_path("tw5/tiddlywiki.js"),
            tiddlywiki_info=tiddlywiki_info
        )
        wiki_folder.start()
        yield wiki_folder
        wiki_folder.process.terminate()


@pytest.fixture(scope="function")
def wf(wf_process):
    """CardsDB object that's empty"""
    tw_del.all_tiddlers(host=wf_process.host, port=wf_process.port)
    yield wf_process


@pytest.fixture(scope="function")
def wf_universal(wf):
    populate_wf(wf, "universal")
    yield wf
