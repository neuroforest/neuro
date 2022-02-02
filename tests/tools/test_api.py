"""
Unit tests for the package neuro.tools.api.
"""

import pytest

from neuro.tools.api import tw_get

from ..helper import PORT


class TestTwGet:
    @pytest.mark.integration
    def test_get_tiddler(self):
        tiddler = tw_get.tiddler("test", port=PORT)
        assert tiddler["title"] == "test"

    @pytest.mark.integration
    def test_get_tw_index(self):
        tw_index = tw_get.tw_index("[all[]]", port=PORT)
        assert type(tw_index) == list
        assert len(tw_index) > 0
        assert all([True if set(d.keys()).issubset({"title", "tmap.id", "tags"}) else False for d in tw_index])

    @pytest.mark.integration
    def test_get_tw_fields(self):
        fields = ["title", "created"]
        tw_fields = tw_get.tw_fields(fields, "[all[]]", port=PORT)
        assert type(tw_fields) == list
        assert len(tw_fields) > 0
        assert all([True if set(d.keys()).issubset(set(fields)) else False for d in tw_fields])