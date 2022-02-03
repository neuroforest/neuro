"""
Unit tests for the package neuro.tools.api.
"""

import pytest
import time

from ..helper import PORT


class TestTwGet:
    @pytest.mark.integration
    def test_get_tiddler(self):
        from neuro.tools.api import tw_get
        tiddler = tw_get.tiddler("test", port=PORT)
        assert tiddler["title"] == "test"

    @pytest.mark.integration
    def test_get_tw_index(self):
        from neuro.tools.api import tw_get
        tw_index = tw_get.tw_index("[all[]]", port=PORT)
        assert type(tw_index) == list
        assert len(tw_index) > 0
        assert all([True if set(d.keys()).issubset({"title", "tmap.id", "tags"}) else False for d in tw_index])

    @pytest.mark.integration
    def test_get_tw_fields(self):
        from neuro.tools.api import tw_get
        fields = ["title", "created"]
        tw_fields = tw_get.tw_fields(fields, "[all[]]", port=PORT)
        assert type(tw_fields) == list
        assert len(tw_fields) > 0
        assert all([True if set(d.keys()).issubset(set(fields)) else False for d in tw_fields])


class TestTwPut:
    @pytest.mark.integration
    def test_put_tiddler(self):
        from neuro.tools.api import tw_get, tw_put
        text = f"text{time.time()}"
        tw_put.tiddler({"title": "put_test", "text": text}, port=PORT)
        tiddler = tw_get.tiddler("put_test", port=PORT)
        assert tiddler["text"] == text

    def test_put_neuro_tid(self):
        from neuro.tools.api import tw_get, tw_put
        from neuro.core import tid
        text = f"text{time.time()}"
        neuro_tid = tid.NeuroTid("test_put_neuro_tid", fields={"text": text})
        tw_put.neuro_tid(neuro_tid, port=PORT)
        tiddler = tw_get.tiddler("test_put_neuro_tid", port=PORT)
        assert tiddler["text"] == text
