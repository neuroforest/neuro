"""
Unit tests of the module neuro.core.data.dict
"""


class TestDictUtils:
    def test_display_string(self, test_file):
        from neuro.core.data.dict import DictUtils
        test_dict = test_file.dict("input/files/text.json")
        display_string = DictUtils.represent(test_dict, display=False)
        result_path = test_file.get("results/files/display-string.txt")
        with open(result_path) as f:
            result_text = f.read()

        assert display_string == result_text

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

    def test_sort_alpha(self, test_file):
        from neuro.core.data.dict import DictUtils
        test_dict = test_file.dict("input/files/text.json")
        sorted_dict = DictUtils.sort_alpha(test_dict)
        assert next(iter(sorted_dict)) == "books view split pane state"

    def test_remove_keys(self, test_file):
        from neuro.core.data.dict import DictUtils
        test_dict = test_file.dict("input/files/text.json")
        test_dict = DictUtils.remove_keys(test_dict, ["kind"])
        assert "kind" not in test_dict

    def test_lod_to_lol(self, test_file):
        from neuro.core.data.dict import DictUtils
        test_dict = test_file.dict("input/files/lod.json")
        lol = DictUtils.lod_to_lol(test_dict)
        assert lol[0][2] == "g.lat"
        assert lol[2][1] == 13.7479
        assert len(lol) == 4
        assert all(len(li) == 5 for li in lol)
