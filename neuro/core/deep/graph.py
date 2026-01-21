import uuid

from neuro.core.data.dict import DictUtils
from neuro.core.deep.object import Object
from neuro.utils import oop_utils


class Node(Object):
    """
    Node represents the specific position of a node inside primary tree
    and the NeuroForest platform.
    """
    def __init__(self, labels: list, **kwargs):
        super().__init__(labels=labels)
        self.uuid = kwargs.get("uuid", self.generate_neuro_id())
        self.properties = kwargs.get("properties", dict())

    def __eq__(self, other):
        if isinstance(other, Node):
            return other.uuid == self.uuid
        else:
            return False

    def __getitem__(self, item):
        return getattr(self, item)

    def __hash__(self):
        return int(self.uuid, 16)

    def __repr__(self, ignore=tuple()):
        """
        Display the node data in the terminal.
        :return:
        """
        attrs_keys = oop_utils.get_attr_keys(self, modes={"no_func", "simple"})

        attrs = {k: self[k] for k in attrs_keys if k not in ignore}
        return DictUtils.represent(attrs, display=False)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __str__(self):
        return str(self.__repr__())

    @classmethod
    def from_neurobase(cls, nb, neuro_id):
        query = f"""
        MATCH (o {{`neuro.id`: "{neuro_id}"}})
        RETURN properties(o) as properties, labels(o) as labels;
        """
        data = nb.get_data(query)
        assert len(data) == 1
        properties = data[0]["properties"]
        labels = data[0]["labels"]
        return cls(labels, uuid=neuro_id, properties=properties)

    def display(self):
        print(self.__repr__())

    @staticmethod
    def generate_neuro_id():
        """
        Generate NeuroID.
        """
        return uuid.uuid4().__str__()

    def get_methods(self):
        method_dict = dict()
        attr_dict = self.to_dict()
        for attr_name in attr_dict:
            type_name = type(attr_dict[attr_name]).__name__
            if type_name == "method":
                method_dict[attr_name] = attr_dict[attr_name]
        return method_dict

    def to_dict(self):
        attrs = oop_utils.get_attr_keys(self)
        attr_dict = dict()
        for attr_name in attrs:
            attr_dict[attr_name] = getattr(self, attr_name)
        return attr_dict
