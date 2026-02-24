import neo4j

from collections import UserDict

from neuro.core import Tiddler
from neuro.core.data.list import ListUtils
from neuro.core.data.dict import DictUtils
from neuro.core.data.str import Uuid
from neuro.utils import terminal_style


class Metaproperty:
    """
    Metaproperty is an object that defines a property of any node in NeuroBase.
    """
    def __init__(self, metaproperty_dict):
        self.label = metaproperty_dict["property"]
        self.node = metaproperty_dict["node"]
        self.node_object = metaproperty_dict["node_object"]
        self.property = metaproperty_dict["property_object"]
        self.property_type = metaproperty_dict["property_type"]
        self.relationship_type = metaproperty_dict["relationship_type"]

    def __repr__(self):
        return (f"<Metaproperty \"{self.label}\" type={self.property_type} "
                f"r={self.relationship_type} node={self.node}>")

    def display(self):
        return DictUtils.represent({
            "label": self.label,
            "relationship_type": self.relationship_type,
            "node_label": self.node,
            "property_type": self.property_type,
        })

    def check(self, property_value):
        check_map = {
            "DateTime": self.check_datetime,
            "OntologyProperty": self.check_ontology_property,
            "String": str.isalpha,
            "Title": Tiddler.is_valid_title,
            "Uuid": Uuid.is_valid_uuid_v4
        }
        handler = check_map.get(self.property_type)

        if handler:
            # noinspection PyArgumentList
            return handler(property_value)
        else:
            print(f"Property not verified: {self.label} (type={self.property_type})")
            return True

    def check_datetime(self, property_value):
        try:
            assert property_value is neo4j.time.DateTime, f"Property {self.label} is not DateTime"
            return True
        except AssertionError:
            return False

    def check_ontology_property(self, property_value):
        print(f"Property not subcategorized: {self.label}")
        return False


class Metaproperties(UserDict):
    def __init__(self, node_label):
        super().__init__()
        self.node_label = node_label

    def __setitem__(self, property_label, metaproperty_object: Metaproperty):
        if property_label in self:
            return
        else:
            super().__setitem__(property_label, metaproperty_object)

    def __repr__(self):
        return f"<Metaproperties node={self.node_label} len={len(self.data)}>"

    @classmethod
    def from_ontology(cls, nb, node_label):
        """Query the ontology and return Metaproperties for a given node label."""
        query = f"""
        MATCH (ion:OntologyNode {{label: "{node_label}"}})
        MATCH (ion)-[:SUBCLASS_OF*0..]->(on)
        MATCH (or:OntologyRelationship)-[:SUBCLASS_OF*0..]->
            (:OntologyRelationship {{label: "HAS_PROPERTY"}})
        MATCH (iop:OntologyNode {{label: "OntologyProperty"}})
        MATCH (op)-[:SUBCLASS_OF*0..]->(iop)

        MATCH (on)-[r]-(p)
        WHERE type(r) = or.label AND op.label IN labels(p)
        RETURN
            on as node_object,
            on.label as node,
            p as property_object,
            type(r) as relationship_type,
            op.label as property_type,
            p.label as property;
        """
        data = nb.get_data(query)
        metaproperties = cls(node_label)
        for mp in data:
            metaproperties[mp["property"]] = Metaproperty(mp)
        return metaproperties

    def display(self):
        return DictUtils.represent(self.data)

    def validate_properties(self, properties: dict, violations=None):
        """
        Check if the node properties conform to the metaproperties.
        :param properties: dict
        :param violations: Violations
        :return:
        """
        if not violations:
            violations = Violations()
        for property_key, property_value in properties.items():
            if property_key not in self.data:
                violations.undefined_properties.append(property_key)
            else:
                val = self.data[property_key].check(property_value)
                if not val:
                    violations.invalid_properties.append((property_key, self.data[property_key]))
                else:
                    print("Property valid:", property_key)

        for p in self.data.values():
            if p.relationship_type == "REQUIRE_PROPERTY" and p.label not in properties:
                violations.missing_properties.append((p.label, p))

        return violations


class OntologyNodeInfo:
    def __init__(self, nb, label):
        self.nb = nb
        self.label = label
        self.lineage: list
        self.relationships: list
        self.metaproperties: Metaproperties
        self.get_lineage()
        self.get_metaproperties()
        self.get_relationships()

    def get_lineage(self):
        query = f"""
        MATCH (ion:OntologyNode {{label: "{self.label}"}})
        MATCH (ion)-[:SUBCLASS_OF*0..]->(on:OntologyNode)
        RETURN on.label as lineage_element
        """
        data = self.nb.get_data(query, parameters={"label": self.label})
        if not data:
            raise ValueError(f"No ontology node found with label: {self.label}")
        self.lineage = [next(iter(record.values())) for record in data]

    def get_metaproperties(self):
        self.metaproperties = Metaproperties.from_ontology(self.nb, self.label)

    def get_relationships(self):
        self.relationships = list()

    def display(self):
        print(f"Ontology info for {terminal_style.BOLD}{self.label}{terminal_style.RESET}")
        print("-" * 50)
        print("Lineage:")
        print("   ", " ➜  ".join(self.lineage))
        print("\nMetaproperties:")
        sorted_metaproperties = sorted(self.metaproperties.values(), key=lambda x: x.label)
        list_represent = ListUtils.represent(sorted_metaproperties, display=False)
        print(list_represent[2:-3])
        print("\nRelationships:")
        list_represent = ListUtils.represent(self.relationships, level=0, display=False)
        print(list_represent[2:-3])


class Violations:
    """
    missing_properties - list of missing required properties
    undefined_properties - list of properties that are not defined in the ontology
    invalid_properties - list of properties with invalid value
    strict - if True, both missing and undefined properties are considered violations
    """
    def __init__(self, strict=True):
        self.undefined_labels = list()
        self.missing_properties = list()
        self.undefined_properties = list()
        self.invalid_properties = list()
        self.strict = strict

    def __add__(self, other):
        self.missing_properties.extend(other.missing_properties)
        self.undefined_properties.extend(other.undefined_properties)
        self.invalid_properties.extend(other.invalid_properties)
        return self

    def __bool__(self):
        if self.strict:
            return bool(
                self.missing_properties
                or self.undefined_properties
                or self.invalid_properties
                or self.undefined_labels
            )
        else:
            return bool(
                self.missing_properties
                or self.invalid_properties
                or self.undefined_labels)

    def __repr__(self):
        return (f"\nMissing properties: {ListUtils.represent(self.missing_properties, display=False)}"
                f"Undefined properties: {ListUtils.represent(self.undefined_properties, display=False)}"
                f"Invalid properties: {ListUtils.represent(self.invalid_properties, display=False)}"
                f"Invalid Labels: {ListUtils.represent(self.undefined_labels, display=False)}")

    def __str__(self):
        return self.__repr__()


class OntologyViolations:
    """Structured ontology-level validation result with categorized violations."""

    def __init__(self):
        self.orphan_nodes: list[str] = []
        self.undefined_labels: list[str] = []
        self.undefined_relationships: list[str] = []
        self.missing_properties: list[tuple] = []
        self.redundant_labels: list[str] = []
        self.redundant_relationships: list[str] = []
        self.redundant_properties: list[str] = []

    def __bool__(self):
        return bool(
            self.orphan_nodes
            or self.undefined_labels
            or self.undefined_relationships
            or self.missing_properties
            or self.redundant_labels
            or self.redundant_relationships
            or self.redundant_properties
        )

    def __repr__(self):
        sections = []
        if self.orphan_nodes:
            sections.append(f"Orphan nodes: {self.orphan_nodes}")
        if self.undefined_labels:
            sections.append(f"Undefined labels: {self.undefined_labels}")
        if self.undefined_relationships:
            sections.append(f"Undefined relationships: {self.undefined_relationships}")
        if self.missing_properties:
            sections.append(f"Missing properties: {self.missing_properties}")
        if self.redundant_labels:
            sections.append(f"Redundant labels: {self.redundant_labels}")
        if self.redundant_relationships:
            sections.append(f"Redundant relationships: {self.redundant_relationships}")
        if self.redundant_properties:
            sections.append(f"Redundant properties: {self.redundant_properties}")
        if not sections:
            return "OntologyViolations(none)"
        return "OntologyViolations(\n  " + "\n  ".join(sections) + "\n)"
