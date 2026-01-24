"""
Unit tests of the module neuro.core.tid
"""

import json

import pytest

from neuro.utils import exceptions

from ..helper import get_test_file


class TestTiddler:
    @staticmethod
    def get_test_tiddler():
        from neuro.core.tid import Tiddler
        tiddler_html_path = get_test_file("input/files/tiddler_html.txt")
        with open(tiddler_html_path) as f:
            tiddler_html = f.read()
        tiddler = Tiddler.from_html(tiddler_html)
        return tiddler

    def test_add_tag(self):
        from neuro.core.tid import Tiddler
        tiddler = Tiddler("test")

        # There should not be 'tags' field by default
        with pytest.raises(KeyError):
            tiddler.fields["tags"]

        # Test adding a tag
        tiddler.add_tag("test_tag")
        assert tiddler.fields["tags"][0] == "test_tag"

        # Test adding tag list
        tiddler.add_tag(["test_tag1", "test_tag2"])
        assert len(tiddler.fields["tags"]) == 3

    def test_from_html(self):
        from neuro.core.tid import Tiddler
        tiddler = self.get_test_tiddler()

        assert tiddler.fields["text"].endswith("%#@&^&(_(+€€\n")

        with pytest.raises(exceptions.InternalError):
            Tiddler.from_html("test")

    def test_from_fields(self):
        from neuro.core.tid import Tiddler
        tiddler_json = get_test_file("input/files/tiddler.json")
        with open(tiddler_json) as f:
            fields = json.load(f)

        tiddler = Tiddler.from_fields(fields)
        assert tiddler.title == "$:/plugins/neuroforest/front/images/Wikipedia"

        del fields["text"]
        tiddler = Tiddler.from_fields(fields)
        assert tiddler

        del fields["title"]
        with pytest.raises(exceptions.MissingTitle):
            Tiddler.from_fields(fields)

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
        tiddler = Tiddler("test")
        assert "test" not in tiddler
        assert "title" in tiddler
        tiddler["test"] = "Lorem"
        assert "test" in tiddler
        del tiddler["test"]
        assert tiddler.fields == {}

    def test_to_text(self):
        tiddler = self.get_test_tiddler()
        text = tiddler.to_text()
        result_text_path = get_test_file("results/files/tiddler_text.txt")
        with open(result_text_path) as f:
            result_text = f.read()
        assert result_text == text


class TestTiddlerList:
    def test_list(self):
        from neuro.core.tid import Tiddler, TiddlerList

        # Test function TiddlerList.extend and TiddlerList.append
        tiddler_3 = Tiddler("test3")
        tiddler_list = TiddlerList([
            Tiddler("test1"),
            Tiddler("test2"),
            tiddler_3
        ])
        assert len(tiddler_list) == 3
        assert "test2" in tiddler_list
        assert tiddler_list.index(tiddler_3) == 2

        # Test function TiddlerList.remove
        tiddler_list.remove("test2")
        assert "test2" not in tiddler_list
        assert len(tiddler_list) == 2
        assert len(tiddler_list) == len(tiddler_list.tiddler_index)

    def test_chain(self):
        from neuro.core.tid import Tiddler, TiddlerList
        tiddler_list = TiddlerList()
        tiddler_list.extend([
            Tiddler("test1"),
            Tiddler("test2"),
            Tiddler("test3")
        ])
        tiddler_list.chain()
        tiddler_2 = tiddler_list[1]
        assert tiddler_2.fields["neuro.primary"] == "test1"
        assert "test1" in tiddler_2.fields["tags"]

    def test_itegrity(self):
        """
        Ensure the property `neuro
        :return:
        """
        from neuro.core.tid import Tiddler, TiddlerList
        tiddler_list = TiddlerList()
        tiddler_list.extend([
            Tiddler("test1"),
            Tiddler("test2"),
            Tiddler("test3")
        ])
        tiddler_list[1].fields["text"] = "Positive."
        assert tiddler_list.tiddler_index["test2"].fields["text"] == "Positive."


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
