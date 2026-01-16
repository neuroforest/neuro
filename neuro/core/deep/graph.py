import uuid

from neuro.core.data.dict import DictUtils
from neuro.core import NeuroObject
from neuro.utils import oop_utils


class Edge(NeuroObject):
    def __init__(self, source, target):
        super().__init__()
        self.weight = 0
        self.source = source
        self.target = target

    def __str__(self):
        string = "{} --> {}"
        return string.format(
            self.source.name,
            self.target.name)

    def apply_to(self, neuro_nodes):
        for neuro_node in neuro_nodes:
            edges = neuro_node.edges
            if self not in edges:
                edges.append(self)


class Edges(list):
    """
    NeuroEdges is an array of object of type NeuroEdgs with some special
    functionality.
    """
    def __init__(self, edges=None):
        self.edges = edges
        if self.are_edges_ok():
            super().__init__(edges)
        else:
            super().__init__()

    def __str__(self):
        collected_string = str()
        for edge in self:
            collected_string += edge.__str__() + "\n"
        return collected_string

    def are_edges_ok(self):
        """
        Checks if edges given at construction are valid.
        :return:
        """
        try:
            it = iter(self.edges)
            for i in it:
                if not isinstance(i, Edge):
                    return False
            return True
        except TypeError:
            return False

    def get_edge(self, edge_type):
        """
        Returns an edge
        :param edge_type:
        :return:
        :rtype:
        """
        for edge in self:
            print(edge.type)
            if edge.type == edge_type:
                return edge

    def get_primary(self):
        return self.get_edge("primary")


class NeuroNode(NeuroObject):
    """
    NeuroNode represents the specific position of a node inside primary tree
    and the NeuroForest platform.
    """
    def __init__(self, **kwargs):
        self.uuid = kwargs.get("uuid", self.generate_neuro_id())
        self.edges = kwargs.get("edges", Edges())

    def __eq__(self, other):
        if isinstance(other, NeuroNode):
            return other.uuid == self.uuid
        else:
            return NotImplemented

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
        return str(self.uuid)

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
