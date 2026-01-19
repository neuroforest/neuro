from neuro.base.api import NeuroBase
from neuro.core.data.list import ListUtils


def validate_label(label):
    query = """
    MATCH (n:OntologyNode {label: $label})
    RETURN n;
    """
    nb = NeuroBase()
    ontology_node = nb.get_data(query, parameters={"label": label})
    assert len(ontology_node) == 1


def validate_property(label, property_name):
    query = """
    MATCH (n:OntologyNode {label: $label})-[:HAS_PROPERTY]->(p:OntologyProperty {label: $property_name})
    RETURN p;
    """
    nb = NeuroBase()
    ontology_property = nb.get_data(
        query, parameters={"label": label, "property_name": property_name}
    )
    assert len(ontology_property) == 1


class ValidateOntology:
    def __init__(self, nb):
        self.nb = nb

    def validate_properties(self):
        query = """
        MATCH (p:OntologyProperty)
        RETURN properties(p) as properties;
        """
        op_ontology = NodeOntology(self.nb, "OntologyProperty")

        properties = self.nb.get_data(query)
        for p in properties:
            property_properties = p["properties"]
            label = p["properties"]["label"]
            validation_result = op_ontology.validate_properties(property_properties)
            if validation_result:
                raise ValueError(f"Invalid metaproperties of {label}:{validation_result}")


class NodeOntology:
    def __init__(self, nb: NeuroBase, label):
        self.nb = nb
        self.label = label
        self.lineage = list()
        self.properties = dict()
        self.relationships = list()
        self.traverse_ontology(label)

    def traverse_ontology(self, current_label):
        self.lineage.append(current_label)
        subclass_query = f"""
        MATCH (o:OntologyNode {{label: "{current_label}"}})
        MATCH (o)-[r:SUBCLASS_OF]->(t)
        RETURN t.label as label;
        """
        subclass_data = self.nb.get_data(subclass_query)
        properties_query = f"""
        MATCH (o:OntologyNode {{label: "{current_label}"}})
        MATCH (o)-[r]->(p:OntologyProperty)
        RETURN type(r) as type, p.label as property
        """
        properties_data = self.nb.get_data(properties_query)
        outgoing_relationship_query = f"""
        MATCH (o:OntologyNode {{label: "{current_label}"}})
        MATCH (o)-[:HAS_RELATIONSHIP]->(r:OntologyRelationship)-[:HAS_TARGET]->(t)
        RETURN r.label as relationship, t.label as target;
        """
        relationship_data = self.nb.get_data(outgoing_relationship_query)
        for r in relationship_data:
            self.relationships.append((r["relationship"], "outgoing", r["target"], current_label),)
        incoming_relationship_query = f"""
        MATCH (o:OntologyNode {{label: "{current_label}"}})
        MATCH (t)-[:HAS_RELATIONSHIP]->(r:OntologyRelationship)-[:HAS_TARGET]->(o)
        RETURN r.label as relationship, t.label as target;
        """
        relationship_data = self.nb.get_data(incoming_relationship_query)
        for r in relationship_data:
            self.relationships.append((r["relationship"], "incoming", r["target"], current_label),)

        if properties_data:
            property_map = {
                "HAS_PROPERTY": "defined",
                "REQUIRE_PROPERTY": "required"
            }
            for p in properties_data:
                property_type = p["type"]
                property_label = p["property"].strip("`")
                if property_label not in self.properties:
                    self.properties[property_label] = [property_map[property_type], current_label]

        if subclass_data:
            subclass_label = subclass_data[0]["label"].strip("`")
            self.traverse_ontology(subclass_label)

    def validate_properties(self, properties):
        validation_result = ValidationResult()
        # Check all required properties are present
        for property_name in self.properties:
            if self.properties[property_name][0] == "required" and property_name not in properties:
                validation_result.missing.append((property_name, self.properties[property_name][1]))

        # Check all properties are defined in the ontology
        for property_name in properties.keys():
            if property_name not in self.properties:
                validation_result.undefined.append((property_name, self.label))

        return validation_result


class ValidationResult:
    def __init__(self, strict=True):
        self.missing = list()
        self.undefined = list()
        self.strict = strict

    def __add__(self, other):
        self.missing.extend(other.missing)
        self.undefined.extend(other.undefined)
        return self

    def __bool__(self):
        if self.strict:
            return bool(self.missing or self.undefined)
        else:
            return bool(self.missing)

    def __repr__(self):
        return (f"\nMissing: {ListUtils.represent(self.missing, display=False)}"
                f"Undefined: {ListUtils.represent(self.undefined, display=False)}")
