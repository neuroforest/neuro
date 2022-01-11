"""
Dictionary methods.
"""

import copy


class DictUtils:
    @staticmethod
    def add_value(d, name, value):
        """
        Add value to the object and look for conflict.
        """
        if name not in d.keys() or d[name] == value:
            d[name] = value

        return d

    @staticmethod
    def add_values(d, name, value):
        """
        Add dictionary to dictionary recursively, without overriding.
        :param d:
        :param name:
        :param value:
        """
        if type(value) == dict:
            if name not in d:
                d[name] = dict()
            for subkey, subname in value.items():
                d[name] = DictUtils.add_values(d[name], subkey, subname)
        else:
            d = DictUtils.add_value(d, name, value)

        return d

    @staticmethod
    def display(d, level=0):
        """
        Displays a dictionary neatly.
        :param d: dictionary to be displayed
        :param level
        """
        # Determine the size f key values.
        max_len = 0
        for key in d:
            key_len = len(key)
            if key_len > max_len:
                max_len = key_len

        dictionary = DictUtils.sort_alpha(d)
        for key in dictionary:
            val = dictionary[key]

            pretty_key = str("{:<" + str(max_len + 3) + "}").format(str(key) + " :")
            if type(val) == dict:
                print(level * "    ", pretty_key, end="\n")
                DictUtils.display(val, level=level + 1)
            elif type(val) == list:
                print(level * "    ", pretty_key, "[", end="\n")
                for i in val:
                    print((level + 1) * "    ", i, end="\n")
                print(level * "    ", "]")
            else:
                print(level * "    ", pretty_key, val)

    @staticmethod
    def merge_dicts(decrescendo_dicts: list):
        """
        Merges the dicts hierarchically according to dictionary order.

        :param decrescendo_dicts: list of dictionaries to be merged, ordered
            according to dominance
        :return: merged dictionary
        :rtype: dict

        """
        reference_dict = decrescendo_dicts.pop(0)
        final_dict = reference_dict
        for dd in decrescendo_dicts:
            for key in dd:
                final_dict = DictUtils.add_values(final_dict, key, dd[key])

        return final_dict

    @staticmethod
    def remove_keys(d, keys):
        """
        Remove keys recursively.
        :param d:
        :param keys: list of keys
        :return:
        """
        new_json_dict = copy.deepcopy(d)
        for key in d:
            value = d[key]
            if type(value) == dict:
                new_value = DictUtils.remove_keys(value, keys)
                new_json_dict[key] = new_value
            elif type(value) == list and len(value) > 0 and type(value[0]) == dict:
                new_value = list()
                for subvalue in value:
                    temp_value = DictUtils.remove_keys(subvalue, keys)
                    new_value.append(temp_value)
                new_json_dict[key] = new_value
            else:
                if key in keys:
                    del new_json_dict[key]

        return new_json_dict

    @staticmethod
    def sort_alpha(d):
        """
        Sorts the dictionary according to the alphabetical order of its keys.

        :param d: unordered dictionary
        :return: ordered dictionary
        :rtype: dict
        """
        ordered_dict = dict()
        try:
            sorted_keys = sorted(d)
        except TypeError:
            sorted_keys = d

        for key in sorted_keys:
            if type(d[key]) == dict:
                value = DictUtils.sort_alpha(d[key])
            else:
                value = d[key]
            ordered_dict[key] = value

        return ordered_dict
