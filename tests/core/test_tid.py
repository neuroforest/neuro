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
        from neuro.core.tid import Tiddler
        tiddler_html_path = get_test_file("input/files/tiddler_html.txt")
        with open(tiddler_html_path) as f:
            tiddler_html = f.read()
        neuro_tid = Tiddler.from_html(tiddler_html)
        return neuro_tid

    def test_add_tag(self):
        from neuro.core.tid import Tiddler
        neuro_tid = Tiddler("test")

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
        from neuro.core.tid import Tiddler
        neuro_tid = self.get_test_neuro_tid()

        assert neuro_tid.fields["text"].endswith("%#@&^&(_(+€€\n")

        with pytest.raises(exceptions.InternalError):
            Tiddler.from_html("test")

    def test_from_tiddler(self):
        from neuro.core.tid import Tiddler
        tiddler_json = get_test_file("input/files/tiddler.json")
        with open(tiddler_json) as f:
            tiddler = json.load(f)

        neuro_tid = Tiddler.from_fields(tiddler)
        assert neuro_tid.title == "$:/plugins/neuroforest/front/images/Wikipedia"

        del tiddler["text"]
        neuro_tid = Tiddler.from_fields(tiddler)
        assert neuro_tid

        del tiddler["title"]
        with pytest.raises(exceptions.MissingTitle):
            Tiddler.from_fields(tiddler)

    def test_get_tid_file_name(self):
        from neuro.core.tid import Tiddler
        test_tid_title_1 = "$:/core/modules/utils/filesystem.js"
        tid_file_name_1 = Tiddler.get_tid_file_name(test_tid_title_1)
        assert tid_file_name_1 == "$__core_modules_utils_filesystem.js"

        test_tid_title_2 = "tiddler <|>|~|test\\:|\"|"
        tid_file_name_2 = Tiddler.get_tid_file_name(test_tid_title_2)
        assert tid_file_name_2 == "tiddler ______test_____"

    def test_item_handling(self):
        """
        Test special methods __contains__, __delitem__, __getitem__
        and __setitem__.
        """
        from neuro.core.tid import Tiddler
        neuro_tid = Tiddler("test")
        assert "test" not in neuro_tid
        assert "title" in neuro_tid
        neuro_tid["test"] = "Lorem"
        assert "test" in neuro_tid
        del neuro_tid["test"]
        assert neuro_tid.fields == {}

    def test_to_text(self):
        neuro_tid = self.get_test_neuro_tid()
        text = neuro_tid.to_text()
        result_text_path = get_test_file("results/files/tiddler_text.txt")
        with open(result_text_path) as f:
            result_text = f.read()
        assert result_text == text


class TestNeuroTids:
    def test_list(self):
        from neuro.core.tid import Tiddler, TiddlerList

        # Test function TiddlerList.extend and TiddlerList.append
        neuro_tid_3 = Tiddler("test3")
        neuro_tids = TiddlerList([
            Tiddler("test1"),
            Tiddler("test2"),
            neuro_tid_3
        ])
        assert len(neuro_tids) == 3
        assert "test2" in neuro_tids
        assert neuro_tids.index(neuro_tid_3) == 2

        # Test function TiddlerList.remove
        neuro_tids.remove("test2")
        assert "test2" not in neuro_tids
        assert len(neuro_tids) == 2
        assert len(neuro_tids) == len(neuro_tids.tiddler_index)

    def test_chain(self):
        from neuro.core.tid import Tiddler, TiddlerList
        neuro_tids = TiddlerList()
        neuro_tids.extend([
            Tiddler("test1"),
            Tiddler("test2"),
            Tiddler("test3")
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
        from neuro.core.tid import Tiddler, TiddlerList
        neuro_tids = TiddlerList()
        neuro_tids.extend([
            Tiddler("test1"),
            Tiddler("test2"),
            Tiddler("test3")
        ])
        neuro_tids[1].fields["text"] = "Positive."
        assert neuro_tids.tiddler_index["test2"].fields["text"] == "Positive."


class TestNeuroTW:
    def test_from_html(self):
        from neuro.core.tid import TiddlywikiHtml
        tw_html_path = get_test_file("input/wikis/tw5.html")

        neuro_tw = TiddlywikiHtml.from_html(tw_html_path)
        assert len(neuro_tw.tiddler_list) == 9
        assert neuro_tw.__contains__("$:/isEncrypted")
        assert neuro_tw.tiddler_list.tiddler_index["$:/isEncrypted"].fields["text"] == "no"


class TestWikiFolder:
    @pytest.fixture(scope="function", autouse=True)
    def setup(self):
        self.tiddlywiki_info = get_test_file("input/tiddlywiki.info")

    def test_create(self):
        import os
        from neuro.core.tid import WikiFolder
        wf_path = get_test_file("output/wf-test-create", exists=False)
        assert not os.path.exists(wf_path)
        wf = WikiFolder(wf_path, tiddlywiki_info=self.tiddlywiki_info)
        assert wf.validate()

    def test_start(self):
        from neuro.core.tid import WikiFolder
        from neuro.utils import network_utils
        wf_path = get_test_file("output/wf-test-start", exists=False)
        wf = WikiFolder(wf_path, tiddlywiki_info=self.tiddlywiki_info)
        wf.start()
        assert network_utils.is_port_in_use(wf.port, host=wf.host)

    def test_api_exposed(self):
        from neuro.core.tid import WikiFolder
        import requests
        wf_path = get_test_file("output/wf-test-api-exposed", exists=False)
        wf = WikiFolder(wf_path, tiddlywiki_info=self.tiddlywiki_info)
        wf.start()
        response = requests.get(f"http://{wf.host}:{wf.port}/neuro/info", timeout=5)
        assert response.status_code == 200
        info = json.loads(response.text)
        assert type(info["local-path"]) is str
        assert not info["dirty"]
