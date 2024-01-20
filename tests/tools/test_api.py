"""
Unit tests for the package neuro.tools.api.
"""

import pytest
import time

from ..helper import PORT, URL


kwargs = {
    "port": PORT,
    "url": URL
}


class TestTwGet:
    @pytest.mark.integration
    def test_get_tiddler(self):
        from neuro.tools.api import tw_get
        tiddler = tw_get.tiddler("test", **kwargs)
        assert tiddler["title"] == "test"

    @pytest.mark.integration
    def test_get_tw_index(self):
        from neuro.tools.api import tw_get
        tw_index = tw_get.tw_index("[all[]]", **kwargs)
        assert type(tw_index) == list
        assert len(tw_index) > 0
        assert all([True if set(d.keys()).issubset({"title", "tmap.id", "tags"}) else False for d in tw_index])

    @pytest.mark.integration
    def test_get_tw_fields(self):
        from neuro.tools.api import tw_get
        fields = ["title", "created"]
        tw_fields = tw_get.tw_fields(fields, "[all[]]", **kwargs)
        assert type(tw_fields) == list
        assert len(tw_fields) > 0
        assert all([True if set(d.keys()).issubset(set(fields)) else False for d in tw_fields])

        tw_fields = tw_get.tw_fields(["title"], "[search:title:literal,casesensitive[thisistest]]", **kwargs)
        assert tw_fields == [{"title": "thisistest"}]


class TestTwPut:
    @pytest.mark.integration
    def test_put_tiddler(self):
        from neuro.tools.api import tw_get, tw_put
        text = f"text{time.time()}"
        tw_put.tiddler({"title": "put_test", "text": text}, **kwargs)
        tiddler = tw_get.tiddler("put_test", **kwargs)
        assert tiddler["text"] == text

    def test_put_neuro_tid(self):
        from neuro.tools.api import tw_get, tw_put
        from neuro.core import tid
        text = f"text{time.time()}"
        neuro_tid = tid.NeuroTid("test_put_neuro_tid", fields={"text": text})
        tw_put.neuro_tid(neuro_tid, **kwargs)
        tiddler = tw_get.tiddler("test_put_neuro_tid", **kwargs)
        assert tiddler["text"] == text


class TestTwActions:
    @pytest.mark.integration
    def test_merge(self):
        from neuro.tools.api import tw_actions, tw_get
        r = tw_actions.merge_tiddlers(["merge1", "merge2"], **kwargs)
        assert r.status_code == 204
        assert not tw_get.is_tiddler("merge1", **kwargs)
        merged_tiddler = tw_get.tiddler("merge2", **kwargs)
        assert merged_tiddler["text"] == "merge2"

    @pytest.mark.integration
    def test_rename(self):
        from neuro.tools.api import tw_actions, tw_get
        r = tw_actions.rename_tiddler("rename1", "rename2", **kwargs)
        assert r.reason == "OK"
        assert r.status_code == 204
        assert not tw_get.is_tiddler("rename1", **kwargs)
        renamed_tiddler = tw_get.tiddler("rename2", **kwargs)
        assert renamed_tiddler["text"] == "rename1"

    def test_replace(self):
        from neuro.tools.api import tw_actions, tw_get
        r = tw_actions.replace_text("replace1", "replace2", **kwargs)
        assert r.reason == "1 tiddlers affected"
        assert r.status_code == 200
        replaced_tiddler = tw_get.tiddler("replace1", **kwargs)
        assert replaced_tiddler["text"] == "replace2"
        r = tw_actions.replace_text("replace1uncommontext", "replace2", **kwargs)
        assert r.status_code == 500
        assert r.reason == "0 tiddlers affected"
