import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from neuro.core.tid import WikiFolder
from neuro.tools.tw5api import tw_del


@pytest.fixture(scope="package")
def wf_process(test_file):
    """CardsDB object connected to a temporary database"""
    tiddlywiki_info = test_file.get("input/tiddlywiki.info")
    test_port = os.getenv("TEST_PORT")
    with TemporaryDirectory() as temp_wiki_folder:
        shutil.copy(tiddlywiki_info, temp_wiki_folder)
        os.makedirs(Path(temp_wiki_folder) / "tiddlers")
        wiki_folder = WikiFolder(
            temp_wiki_folder,
            port=test_port,
            host="127.0.0.1",
            tw5=Path(os.getenv("TW5")) / "tiddlywiki.js",
            tiddlywiki_info=tiddlywiki_info
        )
        wiki_folder.start()
        yield wiki_folder
        wiki_folder.process.terminate()


def populate_wf(wf, fields_json):
    from neuro.core import TiddlerList
    from neuro.tools.tw5api import tw_put
    tiddler_list = TiddlerList.from_json(fields_json)
    tw_put.tiddler_list(tiddler_list, port=wf.port)


@pytest.fixture(scope="function")
def wf(wf_process):
    """CardsDB object that's empty"""
    tw_del.all_tiddlers(host=wf_process.host, port=wf_process.port)
    yield wf_process


@pytest.fixture(scope="function")
def wf_universal(test_file, wf):
    fields_json = test_file.get("input/tiddlers/universal.json")
    print(fields_json)
    populate_wf(wf, fields_json)
    yield wf


@pytest.fixture(scope="function")
def wf_qa(test_file, wf):
    fields_json = test_file.get("input/tiddlers/qa.json")
    populate_wf(wf, fields_json)
    yield wf


@pytest.fixture(scope="function")
def wf_merge(test_file, wf):
    fields_json = test_file.get("input/tiddlers/merge.json")
    populate_wf(wf, fields_json)
    yield wf


@pytest.fixture(scope="function")
def wf_rename(test_file, wf):
    fields_json = test_file.get("input/tiddlers/rename.json")
    populate_wf(wf, fields_json)
    yield wf


@pytest.fixture(scope="function")
def wf_replace(test_file, wf):
    fields_json = test_file.get("input/tiddlers/replace.json")
    populate_wf(wf, fields_json)
    yield wf


@pytest.fixture(scope="function")
def wf_lineage(test_file, wf):
    fields_json = test_file.get("input/tiddlers/lineage.json")
    populate_wf(wf, fields_json)
    yield wf