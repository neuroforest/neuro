import json
import os

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
        self.deep_node = metaproperty_dict["deep_node"]

    def __repr__(self):
        return (f"<Metaproperty \"{self.label}\" type={self.property_type} "
                f"r={self.relationship_type} node={self.node}>")

    def is_required(self):
        return self.relationship_type == "REQUIRE_PROPERTY"

    def display(self):
        return DictUtils.represent({
            "label": self.label,
            "relationship_type": self.relationship_type,
            "node_label": self.node,
            "property_type": self.property_type,
        })

    def check(self, property_value):
        """Check if property value is valid. Returns True if valid, False otherwise."""
        check_map = {
            "DateTime": self.check_datetime,
            "Label": self.check_label,
            "OntologyProperty": self.check_ontology_property,
            "String": lambda v: isinstance(v, str),
            "Title": Tiddler.is_valid_title,
            "Uuid": Uuid.is_valid_uuid_v4,
        }
        handler = check_map.get(self.property_type)
        if not handler:
            return False
        return bool(handler(property_value))

    def check_datetime(self, property_value):
        return isinstance(property_value, neo4j.time.DateTime)

    def check_label(self, property_value):
        import re
        if not isinstance(property_value, str):
            return False
        patterns = {
            "OntologyNode": r"^[A-Z][a-zA-Z]*$",
            "OntologyRelationship": r"^[A-Z][A-Z_]*$",
            "OntologyProperty": r"^[a-z][a-z._-]*$",
        }
        pattern = patterns.get(self.deep_node)
        if not pattern:
            raise ValueError(f"invalid deep_node: {self.deep_node}")
        return bool(re.match(pattern, property_value))

    def check_ontology_property(self, property_value):
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
        ontology_objects = tuple(json.loads(os.environ["ONTOLOGY_OBJECTS"]))
        query = f"""
        MATCH (ion:OntologyNode {{label: "{node_label}"}})
        MATCH (ion)-[:SUBCLASS_OF*0..]->(on)
        MATCH (or:OntologyRelationship)-[:SUBCLASS_OF*0..]->
            (:OntologyRelationship {{label: "HAS_PROPERTY"}})
        MATCH (iop:OntologyNode {{label: "OntologyProperty"}})
        MATCH (op)-[:SUBCLASS_OF*0..]->(iop)

        OPTIONAL MATCH (ion)-[:SUBCLASS_OF*0..]->(root:OntologyNode)
        WHERE root.label IN {list(ontology_objects)}

        MATCH (on)-[r]-(p)
        WHERE type(r) = or.label AND op.label IN labels(p)
        RETURN
            on as node_object,
            on.label as node,
            p as property_object,
            type(r) as relationship_type,
            op.label as property_type,
            p.label as property,
            root.label as deep_node
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
                mp = self.data[property_key]
                if not mp.check(property_value):
                    reason = f"expected {mp.property_type}, got {property_value}"
                    violations.invalid_properties.append((property_key, reason))

        for p in self.data.values():
            if p.relationship_type == "REQUIRE_PROPERTY" and p.label not in properties:
                violations.missing_properties.append(p)

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
    """Collects categorized violations found during ontology validation."""

    def __init__(self):
        self.undefined_labels: list[str] = []
        self.undefined_properties: list = []
        self.missing_properties: list = []
        self.invalid_properties: list = []

    def __bool__(self):
        return any([
            self.undefined_labels, self.undefined_properties,
            self.missing_properties, self.invalid_properties,
        ])

    def __repr__(self):
        B, RST = terminal_style.BOLD, terminal_style.RESET
        lines = []
        if self.missing_properties:
            lines.append(f"  missing: {[p.label for p in self.missing_properties]}")
        if self.undefined_properties:
            lines.append(f"  undefined: {self.undefined_properties}")
        if self.undefined_labels:
            lines.append(f"  undefined labels: {self.undefined_labels}")
        if self.invalid_properties:
            for p, reason in self.invalid_properties:
                lines.append(f"  invalid value: {B}{p}{RST} ({reason})")
        return "\n".join(lines) if lines else "Violations(none)"

    def __str__(self):
        return self.__repr__()
