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
        if type(value) is dict:
            if name not in d:
                d[name] = dict()
            for subkey, subname in value.items():
                d[name] = DictUtils.add_values(d[name], subkey, subname)
        else:
            d = DictUtils.add_value(d, name, value)

        return d

    @staticmethod
    def represent(d, level=0, display=True, sort=True, ignore_list=False):
        """
        Returns a string used for dictionary representation.
        This is a recursive function.
        :param d: dictionary
        :param level: level of indent
        :param display: print the representation string
        :param sort:
        :param ignore_list:
        """
        representation_string = str()
        sep = " " * 4

        max_len = 0
        for key in d:
            key_len = len(key)
            if key_len > max_len:
                max_len = key_len

        if sort:
            dictionary = DictUtils.sort_alpha(d)
        else:
            dictionary = d
        for key in dictionary:
            val = dictionary[key]
            pretty_key = str("{:<" + str(max_len + 3) + "}").format(str(key) + " :")
            if type(val) is dict:
                representation_string += f"{level * sep}{pretty_key}\n"
                representation_string += DictUtils.represent(val, level=level + 1, display=False)
            elif type(val) is list:
                if ignore_list:
                    representation_string += f"{level * sep}{pretty_key}{val}\n"
                else:
                    representation_string += f"{level * sep}{pretty_key}[\n"
                    for i in val:
                        representation_string += f"{(level + 1) * sep}{i}\n"
                    representation_string += f"{level * sep}]\n"
            elif type(val) is str:
                suffix = ""
                if "\n" in val:
                    line_count = val.count("\n")
                    val = val.split("\n")[0]
                    suffix = f" ... [{line_count} lines]"
                if len(val) < 80 - level * 4:
                    pass
                else:
                    if not suffix:
                        suffix = " ..."
                    val = val[:80-level*4] + suffix
                representation_string += f"{level * sep}{pretty_key}{val + suffix}\n"
            else:
                representation_string += f"{level * sep}{pretty_key}{val}\n"

        if display:
            print(representation_string)
            return None
        else:
            return representation_string

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
            if type(value) is dict:
                new_value = DictUtils.remove_keys(value, keys)
                new_json_dict[key] = new_value
            elif type(value) is list and len(value) > 0 and type(value[0]) is dict:
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
            if type(d[key]) is dict:
                value = DictUtils.sort_alpha(d[key])
            else:
                value = d[key]
            ordered_dict[key] = value

        return ordered_dict

    @staticmethod
    def lod_to_lol(lod):
        """
        Convert list of dictionaries to list of rows.
        :param lod:
        :return: lol, where the first list is the header
        """
        header = list()
        master_list = list()
        for d in lod:
            li = ["" for i in range(len(header))]
            for key, value in d.items():
                try:
                    index = header.index(key)
                    li[index] = value
                except ValueError:
                    li = li + [value]
                    header = header + [key]
                    master_list = [sublist + [""] for sublist in master_list]
            master_list.append(li)
        master_list.insert(0, header)
        return master_list
