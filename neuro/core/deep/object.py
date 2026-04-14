from neuro.core.data.dict import DictUtils


class Object(object):
    def __init__(self, labels=None, properties=None):
        # Set labels
        if labels is None:
            self.labels = list()
        elif isinstance(labels, list):
            self.labels = labels
        else:
            raise TypeError(f"Labels must be a list or None, got {type(labels).__name__}")

        # Set properties
        if properties is None:
            self.properties = dict()
        elif isinstance(properties, dict):
            self.properties = properties
        else:
            raise TypeError(f"Properties must be a dict or None, got {type(properties).__name__}")

    def __repr__(self):
        repr_str = (
            f"Object\n"
            f"Type: {self.labels}\n"
            f"Properties:\n{DictUtils.represent(self.properties, display=False, level=1)}\n"
        )
        return repr_str

    def __str__(self):
        return self.__repr__()

    def display(self):
        print(self.__repr__())
