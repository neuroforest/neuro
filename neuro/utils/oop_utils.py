"""
Object-oriented programming utils.
"""

import re


def get_attr_keys(obj, modes=None):
    """
    Displays all object attributes.

    :param obj: object ot get data about
    :param modes: set of mode keywords
        - according to attribute functionality:
            - "func": only attributes that are callable
            - "no_func": only attributes that are not callable
            - "all_func": "func" + "no_func"
        - according to attribute layer:
            - "simple": not preceded or succeeded by "_"
            - "hidden": attributes whose names start with "_"
            - "builtin": attributes in the form of "__attr_name__"
            - "all_layer": "simple" + "hidden" + "builtin" + unclassified above
    :return: attr_keys
    """
    # Setting the default modes.
    if not modes:
        modes = set()
    func_modes = {"all_func", "func", "no_func"}
    layer_modes = {"all_layer", "simple", "hidden", "builtin"}
    if not modes.intersection(func_modes):
        modes.add("all_func")
    if not modes.intersection(layer_modes):
        modes.add("all_layer")

    attr_keys = dir(obj)
    # Filtering functionality.
    if not modes.intersection({"func", "all_func"}):
        attr_keys = [k for k in attr_keys if not hasattr(getattr(obj, k), "__call__")]
    if not modes.intersection({"no_func", "all_func"}):
        attr_keys = [k for k in attr_keys if hasattr(getattr(obj, k), "__call__")]

    if not modes.intersection({"builtin", "all_layer"}):
        pattern = re.compile("^__([_a-zA-Z]*)__$")
        attr_keys = [k for k in attr_keys if not pattern.match(k)]
    if not modes.intersection({"hidden", "all_layer"}):
        pattern = re.compile("_[a-zA-Z][_a-zA-Z]*")
        attr_keys = [k for k in attr_keys if not pattern.match(k)]
    if not modes.intersection({"simple", "all_layer"}):
        pattern = re.compile("[a-zA-Z][_a-zA-Z]*[a-zA-Z]")
        attr_keys = [k for k in attr_keys if not pattern.match(k)]

    return attr_keys


def represent(obj, level=0, modes=None):
    """
    Return a string used for object representation.
    :param obj: object, practically any python object
    :param level: level of indentation
    :param modes: set of modes (see function get_attr_keys)
    :return: representation string
    """

    def get_max_size(li):
        max_len = 0
        for i in li:
            i_len = len(i)
            if i_len > max_len:
                max_len = i_len
        return max_len

    # Setting th default mode.
    representation_string = str()
    attrs = dict()
    attr_keys = get_attr_keys(obj, modes=modes)

    if isinstance(obj, dict):
        attr_keys.extend(list(obj.keys()))
    elif isinstance(obj, list):
        obj = [str(i) for i in obj]
        attr_keys = obj

    # Handling modes given.
    count = 0
    for attr_key in attr_keys:
        try:
            value = object.__getattribute__(obj, attr_key)
            attrs[attr_key] = value
        except AttributeError:
            try:
                value = obj[attr_key]
                attrs[attr_key] = value
            except KeyError:
                attrs[str(count)] = attr_key
                count += 1

    # Displaying.
    key_len = get_max_size(list(attrs.keys()))
    for attr_key, attr_val in attrs.items():
        pretty_key = str("{:<" + str(key_len + 2) + "}").format(str(attr_key) + ":")
        if (hasattr(attr_val, "display") and attr_key != "__class__") or \
                (isinstance(attr_val, dict) and attr_val):
            representation_string += f"{level*'  '}{pretty_key}\n"
            representation_string += represent(attr_val, modes=modes, level=level + 1)
        else:
            representation_string += f"{level*'  '}{pretty_key}{attr_val}"

    return representation_string
