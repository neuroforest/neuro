"""
Unit tests of the module neuro.core.files.text
"""
import os

import deepdiff
import filecmp
import json
import pytest

from ..helper import get_test_file, get_hash


class TestText:
    def test_read(self):
        from neuro.core.files import text
        data_path = get_test_file("input/files/text.txt")
        with text.Text(data_path) as t:
            txt = t.get_text()

        assert get_hash(txt) == "d15791ad718b73be8fb9013a4292dcc1aa469f04"

    def test_path(self):
        from neuro.core.files import text
        with pytest.raises(FileNotFoundError):
            text.Text(";")


class TestTextCsv:
    data_path = get_test_file("input/files/text_csv.csv")
    data_path_short = get_test_file("input/files/text_csv_short")
    os.makedirs(get_test_file("output/files", exists=False))

    def test_is_identifier(self):
        from neuro.core.files import text
        with text.TextCsv(self.data_path_short) as t:
            identifier = t.is_identifier("policyID")
            assert identifier is True
            identifier = t.is_identifier("statecode")
            assert identifier is False

    def test_to_json(self):
        from neuro.core.files import text
        json_path = get_test_file("output/files/text_json_from_csv.json", exists=False)
        result_json_path = get_test_file("results/files/text_json_from_csv.json")
        with text.TextCsv(self.data_path_short) as t:
            t.to_json("policyID", json_path, mode="local")
        assert filecmp.cmp(json_path, result_json_path)

    def test_merge_files(self):
        from neuro.core.files import text
        file_paths = get_test_file("input/files/text_json_merge", multi=True)
        merged_path = get_test_file("output/files/text_json_merged.json", exists=False)
        result_path = get_test_file("results/files/text_json_merged.json")
        text.TextJson.merge_files(file_paths, merged_path)
        assert deepdiff.DeepDiff(json.load(open(merged_path)), json.load(open(result_path)), ignore_order=True) == {}

    def test_insert_layer(self):
        from neuro.core.files import text
        file_path = get_test_file("input/files/text_json_insert.json")
        inserted_path = get_test_file("output/files/text_json_insert_output.json", exists=False)
        result_path = get_test_file("results/files/text_json_insert_output.json")
        with text.TextJson(file_path) as t:
            t.insert_layer("mirwalk", inserted_path)

        assert filecmp.cmp(inserted_path, result_path)
