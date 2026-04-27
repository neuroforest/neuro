import json
import os
import re

from collections import UserDict

from neuro.base import plugins
from neuro.core.data.list import ListUtils
from neuro.core.data.dict import DictUtils
from neuro.core.data.str import Uuid
from neuro.utils import terminal_style


def _check_label(value, mp):
    patterns = {
        "OntologyNode": r"^[A-Z][a-zA-Z]*$",
        "OntologyRelationship": r"^[A-Z][A-Z_]*$",
        "OntologyProperty": r"^[a-z][a-z._-]*$",
    }
    if not isinstance(value, str):
        return False
    pattern = patterns.get(mp.deep_node)
    if not pattern:
        raise ValueError(f"invalid deep_node: {mp.deep_node}")
    return bool(re.match(pattern, value))


HARDCODED_VALIDATORS = {
    "String": lambda v, _mp: isinstance(v, str),
    "Uuid": lambda v, _mp: Uuid.is_valid_uuid_v4(v),
    "OntologyProperty": lambda _v, _mp: False,
    "Label": _check_label,
}


def has_validator(property_type):
    """True if this property type has a hardcoded or plugin-registered validator."""
    if property_type in HARDCODED_VALIDATORS:
        return True
    return plugins.lookup(property_type) is not None


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

    def has_validator(self):
        """True if this property type has a hardcoded or plugin-registered validator."""
        return has_validator(self.property_type)

    def validate(self, property_value):
        """Check if property value is valid. Returns True if valid, False otherwise.

        Metaontology core types (`String`, `Uuid`, `Label`, `OntologyProperty`)
        are hardcoded — they bootstrap all other validation. Non-core types
        fall back to the plugin registry (`validators.py` next to each ontology);
        unregistered types fail closed (use `has_validator` to distinguish).
        """
        fn = HARDCODED_VALIDATORS.get(self.property_type) or plugins.lookup(self.property_type)
        if fn is None:
            return False
        return bool(fn(property_value, self))


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

    def validate_properties(self, properties: dict, violations=None, strict=False):
        """
        Check if the node properties conform to the metaproperties.

        Unregistered (no validator) types: in non-strict mode, fall back to
        String — pass with a warning if the value is a string, fail otherwise.
        In strict mode, always fail.
        """
        if violations is None:
            violations = Violations()
        for property_key, property_value in properties.items():
            if property_key not in self.data:
                violations.undefined_properties.append(property_key)
            else:
                mp = self.data[property_key]
                if not mp.has_validator():
                    if strict:
                        reason = f"unvalidated data type: {mp.property_type}"
                        violations.invalid_properties.append((property_key, reason))
                    elif isinstance(property_value, str):
                        violations.warnings.append(
                            f"{property_key}: unvalidated data type {mp.property_type}, accepted as String"
                        )
                    else:
                        reason = (
                            f"unvalidated data type: {mp.property_type} "
                            f"(and not String: got {property_value!r})"
                        )
                        violations.invalid_properties.append((property_key, reason))
                elif not mp.validate(property_value):
                    reason = f"expected {mp.property_type}, got {property_value}"
                    violations.invalid_properties.append((property_key, reason))

        for p in self.data.values():
            if p.relationship_type == "REQUIRE_PROPERTY" and p.label not in properties:
                violations.missing_properties.append(p)

        return violations


class Metarelationship:
    """Describes a relationship defined in the ontology for a node type.

    Always stored as (source)-[:label]->(target).
    Direction relative to a given node is deduced from source/target.
    """

    def __init__(self, record):
        self.label = record["relationship"]
        self.source = record["source"]
        self.target = record["target"]
        self.relationship_type = record["relationship_type"]

    def __repr__(self):
        return f"<Metarelationship ({self.source})-[:{self.label}]->({self.target})>"

    def is_required(self):
        return self.relationship_type == "REQUIRE_RELATIONSHIP"

    def direction(self, node_label):
        """Return 'outgoing' or 'incoming' relative to node_label."""
        if self.source == node_label:
            return "outgoing"
        if self.target == node_label:
            return "incoming"
        return None


class Metarelationships(UserDict):
    def __init__(self, node_label):
        super().__init__()
        self.node_label = node_label

    def __repr__(self):
        return f"<Metarelationships node={self.node_label} len={len(self.data)}>"

    @classmethod
    def from_ontology(cls, nb, node_label):
        """Query the ontology and return Metarelationships for a given node label."""
        query = f"""
        MATCH (ion:OntologyNode {{label: "{node_label}"}})
        MATCH (ion)-[:SUBCLASS_OF*0..]->(osource)

        // Outgoing: this node has a relationship to a target
        // Collect link types (HAS_RELATIONSHIP and its subclasses)
        MATCH (linktype:OntologyRelationship)-[:SUBCLASS_OF*0..]->
            (:OntologyRelationship {{label: "HAS_RELATIONSHIP"}})

        // Outgoing: this node has a relationship to a target
        OPTIONAL MATCH (osource)-[olink]->(orel:OntologyRelationship)
        WHERE type(olink) = linktype.label
        OPTIONAL MATCH (orel)-[:HAS_TARGET]->(otarget:OntologyNode)
        WITH ion, collect(DISTINCT {{
            source: osource.label, relationship: orel.label,
            target: otarget.label, relationship_type: type(olink),
            direction: "outgoing"
        }}) as outgoing

        // Incoming: another node has a relationship targeting this node
        MATCH (ion)-[:SUBCLASS_OF*0..]->(itarget)
        MATCH (ilinktype:OntologyRelationship)-[:SUBCLASS_OF*0..]->
            (:OntologyRelationship {{label: "HAS_RELATIONSHIP"}})
        OPTIONAL MATCH (isource:OntologyNode)-[ilink]->(irel:OntologyRelationship)
        WHERE type(ilink) = ilinktype.label AND (irel)-[:HAS_TARGET]->(itarget)
        WITH outgoing, collect(DISTINCT {{
            source: isource.label, relationship: irel.label,
            target: itarget.label, relationship_type: type(ilink),
            direction: "incoming"
        }}) as incoming

        UNWIND (outgoing + incoming) as r
        WITH r WHERE r.relationship IS NOT NULL
        RETURN DISTINCT r.source as source, r.relationship as relationship,
               r.target as target, r.relationship_type as relationship_type,
               r.direction as direction
        """
        data = nb.get_data(query)
        metarelationships = cls(node_label)
        for record in data:
            mr = Metarelationship(record)
            key = record["relationship"] + ":" + record["direction"]
            # Skip duplicate incoming entry for self-referential relationships
            if record["direction"] == "incoming" and mr.source == mr.target:
                outgoing_key = record["relationship"] + ":outgoing"
                if outgoing_key in metarelationships:
                    continue
            metarelationships[key] = mr
        return metarelationships

    def validate_relationships(self, nb, neuro_id, violations):
        """Validate that all relationships on a node comply with the ontology."""
        query = """
        MATCH (n {`neuro.id`: $neuro_id})-[r]->(target)
        WHERE target.`neuro.id` IS NOT NULL
        RETURN type(r) as rel_type, labels(target) as target_labels, "outgoing" as direction
        UNION
        MATCH (source)-[r]->(n {`neuro.id`: $neuro_id})
        WHERE source.`neuro.id` IS NOT NULL
        RETURN type(r) as rel_type, labels(source) as target_labels, "incoming" as direction
        """
        relationships = nb.get_data(query, {"neuro_id": neuro_id})

        present_keys = set()
        for rel in relationships:
            rel_type = rel["rel_type"]
            direction = rel["direction"]
            key = f"{rel_type}:{direction}"
            present_keys.add(key)
            if key not in self.data:
                violations.undefined_relationships.append(
                    (rel_type, direction, rel["target_labels"])
                )
            else:
                mr = self.data[key]
                expected_label = mr.target if direction == "outgoing" else mr.source
                if expected_label not in rel["target_labels"]:
                    violations.invalid_relationships.append(
                        (rel_type, direction, rel["target_labels"], expected_label)
                    )

        for key, mr in self.data.items():
            if mr.is_required() and key not in present_keys:
                violations.missing_relationships.append(mr)

        return violations


class OntologyNodeInfo:
    def __init__(self, nb, label):
        self.nb = nb
        self.label = label
        self.lineage: list
        self.metaproperties: Metaproperties
        self.metarelationships: Metarelationships
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
        self.metarelationships = Metarelationships.from_ontology(self.nb, self.label)

    def display(self):
        print(f"Type info for {terminal_style.BOLD}{self.label}{terminal_style.RESET}")
        print("-" * 50)
        print("Lineage:")
        print("   ", " ➜  ".join(self.lineage))
        print("\nProperties:")
        sorted_metaproperties = sorted(self.metaproperties.values(), key=lambda x: x.label)
        list_represent = ListUtils.represent(sorted_metaproperties, display=False)
        print(list_represent[2:-3])
        print("\nRelationships:")
        sorted_metarelationships = sorted(self.metarelationships.values(), key=lambda x: x.label)
        list_represent = ListUtils.represent(sorted_metarelationships, level=0, display=False)
        print(list_represent[2:-3])


class Violations:
    """Collects categorized violations found during ontology validation."""

    def __init__(self):
        self.undefined_labels: list[str] = []
        self.undefined_properties: list = []
        self.missing_properties: list = []
        self.invalid_properties: list = []
        self.undefined_relationships: list = []
        self.missing_relationships: list = []
        self.invalid_relationships: list = []
        self.warnings: list[str] = []

    def __bool__(self):
        return any([
            self.undefined_labels, self.undefined_properties,
            self.missing_properties, self.invalid_properties,
            self.undefined_relationships, self.missing_relationships,
            self.invalid_relationships,
        ])

    def __repr__(self):
        B, RST = terminal_style.BOLD, terminal_style.RESET
        lines = []
        if self.missing_properties:
            lines.append(f"  missing: {[p.label for p in self.missing_properties]}")
        if self.undefined_properties:
            lines.append(f"  undefined: {self.undefined_properties}")
        if self.undefined_labels:
            quoted = ", ".join(f"'{lb}'" for lb in self.undefined_labels)
            noun = "label" if len(self.undefined_labels) == 1 else "labels"
            lines.append(f"  undefined {noun}: {quoted}")
        if self.invalid_properties:
            for p, reason in self.invalid_properties:
                lines.append(f"  invalid value: {B}{p}{RST} ({reason})")
        if self.undefined_relationships:
            for rel_type, direction, labels in self.undefined_relationships:
                lines.append(f"  undefined relationship: {B}{rel_type}{RST} ({direction}, {labels})")
        if self.missing_relationships:
            lines.append(f"  missing relationships: {[mr.label for mr in self.missing_relationships]}")
        if self.invalid_relationships:
            for rel_type, direction, actual, expected in self.invalid_relationships:
                lines.append(f"  invalid relationship target: {B}{rel_type}{RST} ({direction}, expected {expected}, got {actual})")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  warning: {w}")
        return "\n".join(lines) if lines else "Violations(none)"

    def __str__(self):
        return self.__repr__()
