"""
Unit tests of the module neuro.core.tid
"""

import json

import pytest

from neuro.utils import exceptions

from ..helper import get_test_file, get_hash


class TestNeuroTid:
	@staticmethod
	def get_test_neuro_tid():
		from neuro.core.tid import NeuroTid
		tiddler_html_path = get_test_file("input/tiddler_html.txt")
		with open(tiddler_html_path) as f:
			tiddler_html = f.read()
		neuro_tid = NeuroTid.from_html(tiddler_html)
		return neuro_tid

	def test_from_html(self):
		from neuro.core.tid import NeuroTid
		neuro_tid = self.get_test_neuro_tid()

		assert neuro_tid.text.endswith("%#@&^&(_(+€€\n")

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

	def test_to_text(self):
		neuro_tid = self.get_test_neuro_tid()
		text = neuro_tid.to_text(neuro_tid.fields)
		hash_value = get_hash(text)
		assert hash_value == "b452074fa2535957ab4c078e51ccf6cf915db145"

	def test_get_tid_file_name(self):
		from neuro.core.tid import NeuroTid
		test_tid_title_1 = "$:/core/modules/utils/filesystem.js"
		tid_file_name_1 = NeuroTid.get_tid_file_name(test_tid_title_1)
		assert tid_file_name_1 == "$__core_modules_utils_filesystem.js"

		test_tid_title_2 = "tiddler <|>|~|test\\:|\"|"
		tid_file_name_2 = NeuroTid.get_tid_file_name(test_tid_title_2)
		assert tid_file_name_2 == "tiddler ______test_____"


class TestNeuroTids:
	def test_contain(self):
		from neuro.core.tid import NeuroTid, NeuroTids
		neuro_tids = NeuroTids()
		neuro_tids.extend([
			NeuroTid("test1"),
			NeuroTid("test2"),
			NeuroTid("test3")
		])

		assert len(neuro_tids) == 3
		assert "test2" in neuro_tids

		neuro_tids.remove("test2")
		assert "test2" not in neuro_tids


class TestNeuroTW:
	def test_from_html(self):
		from neuro.core.tid import NeuroTW
		tw_html_path = get_test_file("input/tw.html")
		with open(tw_html_path) as f:
			tw_html = f.read()

		neuro_tw = NeuroTW.from_html(tw_html)
		assert len(neuro_tw.neuro_tids) == 4
		assert neuro_tw.__contains__("$:/isEncrypted")
		assert neuro_tw.neuro_tids.neuro_index["$:/isEncrypted"]["object"]["text"] == "\nno\n"
