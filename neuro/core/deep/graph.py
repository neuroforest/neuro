import uuid

from neuro.core.data.dict import DictUtils
from neuro.core.deep.object import Object
from neuro.utils import oop_utils


class Node(Object):
    """
    Node represents the specific position of a node inside the primary tree
    and the NeuroForest platform.
    """
    def __init__(self, labels: list, **kwargs):
        super().__init__(labels=labels, properties=kwargs.get("properties", dict()))
        if "uuid" in kwargs:
            self.uuid = kwargs["uuid"]
        elif "neuro.id" not in self.properties:
            self.uuid = self.generate_neuro_id()

    @property
    def uuid(self):
        return self.properties.get("neuro.id")

    @uuid.setter
    def uuid(self, value):
        self.properties["neuro.id"] = value

    def __eq__(self, other):
        if isinstance(other, Node):
            return other.uuid == self.uuid
        else:
            return False

    def __getitem__(self, item):
        return getattr(self, item)

    def __hash__(self):
        return int(self.uuid, 16)

    def __repr__(self):
        repr_str = (
            f"Node: {self.uuid}\n"
            f"Type: {self.labels}\n"
            f"Properties:\n{DictUtils.represent(self.properties, display=False, level=1)}\n"
        )
        return repr_str

    def __setitem__(self, key, value):
        setattr(self, key, value)

    @classmethod
    def from_neurobase(cls, nb, neuro_id):
        query = f"""
        MATCH (o {{`neuro.id`: "{neuro_id}"}})
        RETURN properties(o) as properties, labels(o) as labels;
        """
        data = nb.get_data(query)
        assert len(data) == 1
        return cls(data[0]["labels"], properties=data[0]["properties"])

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
