"""
Unit tests of the module neuro.core.data.dict
"""

import pytest

from neuro.core.data.dict import DictUtils


pytestmark = pytest.mark.unit


class TestDictUtils:
    def test_dict_merge(self):
        dict1 = {
            "name": {
                "subname": {
                    "help": "This is help 1",
                    "value": 1500
                }
            }
        }
        dict2 = {
            "name": {
                "subname": {
                    "help": "This is help 2",
                    "value_real": 1600
                }
            }
        }
        expected_merged_dict = {
            "name": {
                "subname": {
                    "help": "This is help 1",
                    "value": 1500,
                    "value_real": 1600
                }
            }
        }
        dict_merged = DictUtils.merge_dicts([dict1, dict2])

        assert expected_merged_dict == dict_merged

    def test_sort_alpha(self):
        test_dict = {"zebra": 1, "apple": 2, "mango": 3}
        sorted_dict = DictUtils.sort_alpha(test_dict)
        assert list(sorted_dict.keys()) == ["apple", "mango", "zebra"]

    def test_remove_keys(self):
        test_dict = {"a": 1, "kind": "field", "nested": {"kind": "inner", "b": 2}}
        result = DictUtils.remove_keys(test_dict, ["kind"])
        assert "kind" not in result
        assert "kind" not in result["nested"]
        assert result["a"] == 1
        assert result["nested"]["b"] == 2

    def test_lod_to_lol(self):
        lod = [
            {"title": "A", "x": 1.0, "y": 2.0},
            {"title": "B", "x": 3.0, "z": 4.0},
        ]
        lol = DictUtils.lod_to_lol(lod)
        assert lol[0] == ["title", "x", "y", "z"]
        assert lol[1] == ["A", 1.0, 2.0, ""]
        assert lol[2] == ["B", 3.0, "", 4.0]
