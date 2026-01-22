"""
Unit tests for the package neuro.tools.api.
"""
import os
import time

import pytest

from neuro.utils import network_utils

from ..helper import create_and_run_wiki_folder


kwargs = {
    "port": os.getenv("TEST_PORT"),
    "host": os.getenv("HOST")
}


@pytest.fixture(scope="module", autouse=True)
def run_wiki_server():
    process = create_and_run_wiki_folder("universal", kwargs.get("port"))
    network_utils.wait_for_socket(kwargs.get("host"), kwargs.get("port"))
    yield
    process.kill()


class TestTwActions:
    def test_merge(self):
        from neuro.tools.tw5api import tw_actions, tw_get
        r = tw_actions.merge_tiddlers(["merge1", "merge2", "merge3"], **kwargs)
        assert r.status_code == 204
        assert not tw_get.is_tiddler("merge1", **kwargs)
        assert not tw_get.is_tiddler("merge2", **kwargs)
        merged_tiddler = tw_get.tiddler("merge3", **kwargs)
        assert merged_tiddler["text"] == "merge3"
        assert merged_tiddler["created"] == "2022-02-04T11:55:42.968Z"
        assert merged_tiddler["merge1"] == "yes"
        assert merged_tiddler["merge2"] == "yes"
        assert merged_tiddler["merge3"] == "yes"

    def test_rename(self):
        from neuro.tools.tw5api import tw_actions, tw_get
        r = tw_actions.rename_tiddler("rename1", "rename2", **kwargs)
        assert r.reason == "0 tiddlers affected"
        assert r.status_code == 200
        assert not tw_get.is_tiddler("rename1", **kwargs)
        renamed_tiddler = tw_get.tiddler("rename2", **kwargs)
        assert renamed_tiddler["text"] == "rename1"

    def test_replace(self):
        from neuro.tools.tw5api import tw_actions, tw_get
        r = tw_actions.replace_text("replace1", "replace2", **kwargs)
        assert r.reason == "1 tiddlers affected"
        assert r.status_code == 200
        replaced_tiddler = tw_get.tiddler("replace1", **kwargs)
        assert replaced_tiddler["text"] == "replace2"
        r = tw_actions.replace_text("replace1uncommontext", "replace2", **kwargs)
        assert r.status_code == 500
        assert r.reason == "0 tiddlers affected"


class TestTwDel:
    def test_del_tiddler(self):
        from neuro.tools.tw5api import tw_del, tw_get
        assert tw_get.is_tiddler("delete", **kwargs) is True
        tw_del.tiddler("delete", **kwargs)
        assert tw_get.is_tiddler("delete", **kwargs) is False


class TestTwGet:
    def test_filter_output(self):
        from neuro.tools.tw5api import tw_get
        tw_filter = "[title[test]get[created]] [title[test]get[neuro.id]]"
        filter_output = tw_get.filter_output(tw_filter, **kwargs)
        assert type(filter_output) is list
        assert len(filter_output) == 2

    def test_get_lineage(self):
        from neuro.tools.tw5api import tw_get
        create_and_run_wiki_folder("lineage", 8069)
        lineage = tw_get.lineage("lineage-root", "[!is[system]]", limit=20, port=8069)
        assert len(lineage["lineage-branch-4"]) == 20
        assert len(lineage["lineage-branch-1-1"]) == 3
        assert lineage["lineage-branch-1-1"][0] == "lineage-root"
        assert "lineage-6-1" not in lineage
        assert "lineage-branch-3-1" not in lineage

    def test_get_neuro_tid(self):
        from neuro.tools.tw5api import tw_get
        neuro_tid = tw_get.neuro_tid("test", **kwargs)
        assert "created" in neuro_tid.fields

    def test_get_tiddler(self):
        from neuro.tools.tw5api import tw_get
        tiddler = tw_get.tiddler("test", **kwargs)
        assert tiddler["title"] == "test"
        assert "created" in tiddler
        assert tiddler["created"] == "2019-01-30T20:02:31.703Z"

    def test_get_tw_index(self):
        from neuro.tools.tw5api import tw_get
        tw_index = tw_get.tw_index("[all[]]", **kwargs)
        assert type(tw_index) is list
        assert len(tw_index) > 0
        assert all([True if set(d.keys()).issubset({"title", "tmap.id", "tags"}) else False for d in tw_index])

    def test_get_tw_fields(self):
        from neuro.tools.tw5api import tw_get
        fields = ["title", "created"]
        tw_fields = tw_get.tw_fields(fields, "[all[]]", **kwargs)
        assert type(tw_fields) is list
        assert len(tw_fields) > 0
        assert all([True if set(d.keys()).issubset(set(fields)) else False for d in tw_fields])

        tw_fields = tw_get.tw_fields(["title"], "[search:title:literal,casesensitive[thisistest]]", **kwargs)
        assert tw_fields == [{"title": "thisistest"}]

    def test_get_tid_titles(self):
        from neuro.tools.tw5api import tw_get
        tid_titles = tw_get.tid_titles("[all[]]", **kwargs)
        assert len(tid_titles) == 21
        assert type(tid_titles[0]) is str


class TestTwPut:
    def test_put_tiddler(self):
        from neuro.tools.tw5api import tw_get, tw_put
        text = f"text{time.time()}"
        tw_put.tiddler({"title": "put_test", "text": text}, **kwargs)
        tiddler = tw_get.tiddler("put_test", **kwargs)
        assert tiddler["text"] == text

    def test_put_neuro_tid(self):
        from neuro.tools.tw5api import tw_get, tw_put
        from neuro.core import tid
        text = f"text{time.time()}"
        neuro_tid = tid.Tiddler("test_put_neuro_tid", fields={"text": text})
        tw_put.neuro_tid(neuro_tid, **kwargs)
        tiddler = tw_get.tiddler("test_put_neuro_tid", **kwargs)
        assert tiddler["text"] == text

    def test_replace_neuro_tid(self):
        from neuro.tools.tw5api import tw_get, tw_put
        nt1 = tw_get.neuro_tid("test", **kwargs)
        tw_put.neuro_tid(nt1, **kwargs)
        nt2 = tw_get.neuro_tid("test", **kwargs)
        from neuro.core.data.dict import DictUtils
        DictUtils.represent(nt1.fields)
        DictUtils.represent(nt2.fields)
        assert nt1 == nt2
