"""
Unit tests of the module neuro.core.data.dict
"""

import json

from ..helper import get_test_file, Capturing, get_hash


class TestDictUtils:
    def get_test_dict(self):
        json_path = get_test_file("input/text.json")
        with open(json_path) as f:
            json_text = f.read()
        self.test_dict = json.loads(json_text)

    def test_display(self):
        from neuro.core.data.dict import DictUtils
        self.get_test_dict()
        with Capturing() as output:
            DictUtils.display(self.test_dict)

        assert get_hash(output.__str__()) == "d37fd89bd289a48031a0b77d8d665800926a1cb6"

    def test_dict_merge(self):
        from neuro.core.data.dict import DictUtils
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
        from neuro.core.data.dict import DictUtils
        self.get_test_dict()
        sorted_dict = DictUtils.sort_alpha(self.test_dict)
        assert next(iter(sorted_dict)) == "books view split pane state"

    def test_remove_keys(self):
        from neuro.core.data.dict import DictUtils
        self.get_test_dict()
        self.test_dict = DictUtils.remove_keys(self.test_dict, ["kind"])
        assert "kind" not in self.test_dict
