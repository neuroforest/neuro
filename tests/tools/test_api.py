"""
Unit tests for the package neuro.tools.api.
"""
import os
import time


kwargs = {
    "port": os.getenv("TEST_PORT"),
    "host": os.getenv("HOST")
}


class TestFixtures:
    def test_wf(self, wf):
        assert wf.port == os.getenv("TEST_PORT")

    def test_wf_universal(self, wf_universal):
        from neuro.tools.tw5api.tw_get import tid_titles
        assert len(tid_titles("[!is[system]]", **kwargs)) == 9


class TestTwActions:
    def test_merge(self, wf_merge):
        from neuro.tools.tw5api import tw_actions, tw_get

        r = tw_actions.merge_tiddlers(["Merge 1", "Merge 2", "Merge Target"], **kwargs)
        assert r.status_code == 204
        assert not tw_get.is_tiddler("Merge 1", **kwargs)
        assert not tw_get.is_tiddler("Merge 2", **kwargs)

        merge_target = tw_get.fields("Merge Target", **kwargs)
        assert merge_target["created"] == "2025-01-23T16:42:27.976Z"
        assert merge_target["field1"] == "merge1"
        assert merge_target["override"] == "2"
        assert merge_target["neuro.id"] == "9bd40ef6-2ec5-4952-abc2-57dd34df847b"

        assert tw_get.fields("Primary", **kwargs)["neuro.primary"] == "Merge Target"
        assert tw_get.fields("Text", **kwargs)["text"] == "[[Merge Target]]"
        assert "|Merge Target]]" in tw_get.fields("Complex Text", **kwargs)["text"]

    def test_rename(self, wf_rename):
        from neuro.tools.tw5api import tw_actions, tw_get
        r = tw_actions.rename_tiddler("Old Name", "New Name", **kwargs)

        assert r.reason == "8 tiddlers affected"
        assert r.status_code == 200
        assert not tw_get.is_tiddler("Old Name", **kwargs)
        assert tw_get.is_tiddler("New Name", **kwargs)

        assert tw_get.fields("Primary", **kwargs)["neuro.primary"] == "New Name"
        assert tw_get.fields("Tag", **kwargs)["tags"] == ["New Name"]
        assert "New Name" in tw_get.fields("MultiTag", **kwargs)["tags"]
        assert tw_get.fields("Text 1", **kwargs)["text"] == "[[New Name]]"
        assert tw_get.fields("Text 2", **kwargs)["text"] == "[[old name|New Name]]"
        complex_text_3 = tw_get.fields("Complex Text 3", **kwargs)["text"]
        assert complex_text_3.count("|New Name]]") == 3
        assert "New Name" in tw_get.fields("List", **kwargs)["list"]
        assert tw_get.fields("Field", **kwargs)["random"] == "Old Name"

    def test_replace(self, wf_replace):
        from neuro.tools.tw5api import tw_actions, tw_get
        old = "LKtdNnjU"
        new = "9L5nBGqv"
        r = tw_actions.replace_text(old, new, **kwargs)
        assert r.reason == "6 tiddlers affected"
        assert tw_get.fields("Primary", **kwargs)["neuro.primary"] == new
        assert tw_get.fields("Tag", **kwargs)["tags"] == [old]
        assert new in tw_get.fields("Text", **kwargs)["text"]
        assert old in tw_get.fields("List", **kwargs)["list"]
        assert new in tw_get.fields("Complex Text", **kwargs)["text"]
        assert tw_get.fields("Field Value", **kwargs)["field"] == new
        assert new in tw_get.fields("Inside Field Value", **kwargs)["test"]
        assert not tw_get.is_tiddler(new, **kwargs)


class TestTwDelete:
    def test_delete_tiddler(self, wf_universal):
        from neuro.tools.tw5api import tw_del, tw_get
        assert tw_get.is_tiddler("delete", **kwargs) is True
        tw_del.tiddler("delete", **kwargs)
        assert tw_get.is_tiddler("delete", **kwargs) is False

    def test_delete_all_tiddlers(self, wf_universal):
        from neuro.tools.tw5api import tw_del, tw_get
        tw_del.all_tiddlers(**kwargs)
        assert len(tw_get.tid_titles(["!is[system]"], **kwargs)) == 0


class TestTwGet:
    def test_filter_output(self, wf_universal):
        from neuro.tools.tw5api import tw_get
        tw_filter = "[title[test]get[created]] [title[test]get[neuro.id]]"
        filter_output = tw_get.filter_output(tw_filter, **kwargs)
        assert type(filter_output) is list
        assert len(filter_output) == 2

    def test_get_lineage(self, wf_lineage):
        from neuro.tools.tw5api import tw_get
        lineage = tw_get.lineage("lineage-root", "[!is[system]]", limit=20, **kwargs)
        assert len(lineage["lineage-branch-4"]) == 20
        assert len(lineage["lineage-branch-1-1"]) == 3
        assert lineage["lineage-branch-1-1"][0] == "lineage-root"
        assert "lineage-6-1" not in lineage
        assert "lineage-branch-3-1" not in lineage

    def test_get_tiddler(self, wf_universal):
        from neuro.tools.tw5api import tw_get
        tiddler = tw_get.tiddler("test", **kwargs)
        assert "created" in tiddler.fields

    def test_get_fields(self, wf_universal):
        from neuro.tools.tw5api import tw_get
        fields = tw_get.fields("test", **kwargs)
        assert fields["title"] == "test"
        assert "created" in fields
        assert fields["created"] == "2019-01-30T20:02:31.703Z"

    def test_get_tw_fields_general(self, wf_universal):
        from neuro.tools.tw5api import tw_get
        fields = ["title", "created"]
        tw_fields = tw_get.tw_fields(fields, "[!is[system]]", **kwargs)
        assert type(tw_fields) is list
        assert len(tw_fields) == 9
        assert all([True if set(d.keys()).issubset(set(fields)) else False for d in tw_fields])

    def test_get_tw_fields_search(self, wf_universal):
        from neuro.tools.tw5api import tw_get
        tw_fields = tw_get.tw_fields(["title"], "[search:title:literal,casesensitive[thisistest]]", **kwargs)
        assert tw_fields == [{"title": "thisistest"}]

    def test_get_tid_titles(self, wf_universal):
        from neuro.tools.tw5api import tw_get
        tid_titles = tw_get.tid_titles("[!is[system]]", **kwargs)
        assert len(tid_titles) == 9
        assert type(tid_titles[0]) is str
        assert "delete" in tid_titles


class TestTwPut:
    def test_put_fields(self, wf):
        from neuro.tools.tw5api import tw_get, tw_put
        text = f"text{time.time()}"
        tw_put.fields({"title": "Put Test", "text": text}, **kwargs)
        fields = tw_get.fields("Put Test", **kwargs)
        assert fields["text"] == text

    def test_put_tiddler(self, wf):
        from neuro.tools.tw5api import tw_get, tw_put
        from neuro.core import Tiddler
        text = f"text{time.time()}"
        tiddler = Tiddler("Test Put Tiddler", fields={"text": text})
        tw_put.tiddler(tiddler, **kwargs)
        tiddler = tw_get.fields("Test Put Tiddler", **kwargs)
        assert tiddler["text"] == text

    def test_replace_tiddler(self, wf_universal):
        from neuro.tools.tw5api import tw_get, tw_put
        nt1 = tw_get.tiddler("test", **kwargs)
        tw_put.tiddler(nt1, **kwargs)
        nt2 = tw_get.tiddler("test", **kwargs)
        assert nt1 == nt2
