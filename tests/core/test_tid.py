"""
Unit tests of the module neuro.core.tid
"""

import json

import pytest

from neuro.utils import exceptions

from ..helper import get_test_file


class TestNeuroTid:
    @staticmethod
    def get_test_neuro_tid():
        from neuro.core.tid import NeuroTid
        tiddler_html_path = get_test_file("input/tiddler_html.txt")
        with open(tiddler_html_path) as f:
            tiddler_html = f.read()
        neuro_tid = NeuroTid.from_html(tiddler_html)
        return neuro_tid

    def test_add_tag(self):
        from neuro.core.tid import NeuroTid
        neuro_tid = NeuroTid("test")

        # There should not be `tags` field by default
        with pytest.raises(KeyError):
            neuro_tid.fields["tags"]

        # Test adding a tag
        neuro_tid.add_tag("test_tag")
        assert neuro_tid.fields["tags"][0] == "test_tag"

        # Test adding tag list
        neuro_tid.add_tag(["test_tag1", "test_tag2"])
        assert len(neuro_tid.fields["tags"]) == 3

    def test_from_html(self):
        from neuro.core.tid import NeuroTid
        neuro_tid = self.get_test_neuro_tid()

        assert neuro_tid.fields["text"].endswith("%#@&^&(_(+€€\n")

        with pytest.raises(TypeError):
            NeuroTid.from_html("test")

    def test_from_tiddler(self):
        from neuro.core.tid import NeuroTid
        tiddler_json = get_test_file("input/tiddler.json")
        with open(tiddler_json) as f:
            tiddler = json.load(f)

        neuro_tid = NeuroTid.from_tiddler(tiddler)
        assert neuro_tid.title == "$:/plugins/neuroforest/front/images/Wikipedia"

        del tiddler["text"]
        neuro_tid = NeuroTid.from_tiddler(tiddler)
        assert neuro_tid

        del tiddler["title"]
        with pytest.raises(exceptions.MissingTitle):
            NeuroTid.from_tiddler(tiddler)

    def test_get_tid_file_name(self):
        from neuro.core.tid import NeuroTid
        test_tid_title_1 = "$:/core/modules/utils/filesystem.js"
        tid_file_name_1 = NeuroTid.get_tid_file_name(test_tid_title_1)
        assert tid_file_name_1 == "$__core_modules_utils_filesystem.js"

        test_tid_title_2 = "tiddler <|>|~|test\\:|\"|"
        tid_file_name_2 = NeuroTid.get_tid_file_name(test_tid_title_2)
        assert tid_file_name_2 == "tiddler ______test_____"

    def test_item_handling(self):
        """
        Test special methods __contains__, __delitem__, __getitem__
        and __setitem__.
        """
        from neuro.core.tid import NeuroTid
        neuro_tid = NeuroTid("test")
        assert "test" not in neuro_tid
        assert "title" in neuro_tid
        neuro_tid["test"] = "Lorem"
        assert "test" in neuro_tid
        del neuro_tid["test"]
        assert neuro_tid.fields == {}

    def test_to_text(self):
        neuro_tid = self.get_test_neuro_tid()
        text = neuro_tid.to_text(neuro_tid.fields)
        result_text_path = get_test_file("results/tiddler_text.txt")
        with open(result_text_path) as f:
            result_text = f.read()

        assert result_text == text


class TestNeuroTids:
    def test_list(self):
        from neuro.core.tid import NeuroTid, NeuroTids

        # Test function NeuroBits.extend and NeuroBits.append
        neuro_tid_3 = NeuroTid("test3")
        neuro_tids = NeuroTids([
            NeuroTid("test1"),
            NeuroTid("test2"),
            neuro_tid_3
        ])
        assert len(neuro_tids) == 3
        assert "test2" in neuro_tids
        assert neuro_tids.index(neuro_tid_3) == 2

        # Test function NeuroBits.remove
        neuro_tids.remove("test2")
        assert "test2" not in neuro_tids
        assert len(neuro_tids) == 2
        assert len(neuro_tids) == len(neuro_tids.object_index)

    def test_chain(self):
        from neuro.core.tid import NeuroTid, NeuroTids
        neuro_tids = NeuroTids()
        neuro_tids.extend([
            NeuroTid("test1"),
            NeuroTid("test2"),
            NeuroTid("test3")
        ])
        neuro_tids.chain()
        neuro_tid_2 = neuro_tids[1]
        assert neuro_tid_2.fields["neuro.primary"] == "test1"
        assert "test1" in neuro_tid_2.fields["tags"]

    def test_itegrity(self):
        """
        Ensure the property `neuro
        :return:
        """
        from neuro.core.tid import NeuroTid, NeuroTids
        neuro_tids = NeuroTids()
        neuro_tids.extend([
            NeuroTid("test1"),
            NeuroTid("test2"),
            NeuroTid("test3")
        ])
        neuro_tids[1].fields["text"] = "Positive."
        assert neuro_tids.object_index["test2"].fields["text"] == "Positive."


class TestNeuroTW:
    def test_from_html(self):
        from neuro.core.tid import NeuroTW
        tw_html_path = get_test_file("input/tw.html")

        neuro_tw = NeuroTW.from_html(tw_html_path)
        assert len(neuro_tw.neuro_tids) == 7
        assert neuro_tw.__contains__("$:/isEncrypted")
        assert neuro_tw.neuro_tids.object_index["$:/isEncrypted"].fields["text"] == "\nno\n"


class TestNeuroWF:
    def test_init(self):
        from neuro.core.tid import NeuroWF
        wf_path = get_test_file("input/wikifolder")
        wf_path_nonexistent = get_test_file("output/nonexistent", exists=False)
        wf = NeuroWF(wf_path)
        assert isinstance(wf, NeuroWF)

        with pytest.raises(exceptions.FileNotWiki):
            NeuroWF(wf_path_nonexistent)

        wf_nonexistent = NeuroWF(wf_path_nonexistent, exists=False)
        assert isinstance(wf_nonexistent, NeuroWF)
