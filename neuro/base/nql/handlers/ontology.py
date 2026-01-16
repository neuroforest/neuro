from neuro.core import NeuroNode, Moment
from neuro.base.api import NeuroBase
from neuro.base.nql.components import NqlTransformer, NqlGenerator
from neuro.core.data.dict import DictUtils
from neuro.core.data.list import ListUtils
from neuro.utils import terminal_style


NB = NeuroBase()


def handle_node(data):
    label = data["label"]
    ontology_label = "Ontology" + data["type"].title()
    properties = {
        "label": label,
        **data["properties"]
    }
    properties_string = NqlGenerator().properties_string(properties)
    match_query = f"""
           MATCH (o:{ontology_label} {properties_string})
           RETURN o;
       """

    match_data = NB.get_data(match_query)
    if match_data:
        print("Nothing to add.")
        return

    properties = {
        "neuro.id": NeuroNode.generate_neuro_id(),
        "title": f".ontology {label}",
        **data["properties"]
    }
    properties_string = NqlGenerator().properties_string(properties)
    current_iso_z = Moment().to_iso_z()
    merge_query = f"""
           MERGE (o:{ontology_label} {{label: "{label}"}})
           ON CREATE SET
               o += {properties_string},
               o.created = "{current_iso_z}",
               o.modified = "{current_iso_z}"
           ON MATCH SET
               o += {properties_string},
               o.modified = "{current_iso_z}";
       """
    NB.run_query(merge_query)


def handle_connect(data, relationship_type):
    properties = {
        "label": data["label"],
        **data["properties"]
    }
    properties_string = NqlGenerator().properties_string(properties)
    target_properties = {
        "label": data["target_node"]["label"],
        **data["target_node"]["properties"]
    }
    target_properties_string = NqlGenerator().properties_string(target_properties)
    query = f"""
        MATCH (o {properties_string})
        MATCH (t {target_properties_string})
        OPTIONAL MATCH (o)-[e:{relationship_type}]->(t)
        MERGE (o)-[r:{relationship_type}]->(t)
        RETURN o, t, e;
    """

    return_data = NB.get_data(query)
    if not return_data:
        print("Incorrect ontology nodes given.")
    elif return_data[0]["e"]:
        print("Property already set.")


def handle_set_relationship(data):
    properties = {
        "label": data["label"],
        **data["properties"]
    }
    properties_string = NqlGenerator().properties_string(properties)
    relationship_properties = {
        "label": data["relationship_node"]["label"],
        **data["relationship_node"]["properties"]
    }
    relationship_properties_string = NqlGenerator().properties_string(relationship_properties)
    target_properties = {
        "label": data["target_node"]["label"],
        **data["target_node"]["properties"]
    }
    target_properties_string = NqlGenerator().properties_string(target_properties)

    query = f"""
        MATCH (o:OntologyNode {properties_string})
        MATCH (r:OntologyRelationship {relationship_properties_string})
        MATCH (t:OntologyNode {target_properties_string})
        OPTIONAL MATCH (o)-[er:HAS_RELATIONSHIP]->(r)-[et:HAS_TARGET]->(t)
        MERGE (o)-[:HAS_RELATIONSHIP]->(r)
        MERGE (r)-[:HAS_TARGET]->(t)
        RETURN o, r, t, er, et;
    """

    return_data = NB.get_data(query)

    if not return_data:
        print("Incorrect ontology nodes given.")
    elif return_data[0]["er"] and return_data[0]["et"]:
        print("Relationship already set.")


def traverse_ontology(label, lineage, properties, relationships):
    subclass_query = f"""
        MATCH (o:OntologyNode {{label: "{label}"}})
        MATCH (o)-[r:SUBCLASS_OF]->(t)
        RETURN t.label as label;
    """
    subclass_data = NB.get_data(subclass_query)
    properties_query = f"""
        MATCH (o:OntologyNode {{label: "{label}"}})
        MATCH (o)-[r]->(p:OntologyProperty)
        RETURN type(r) as type, p.label as property
    """
    properties_data = NB.get_data(properties_query)
    outgoing_relationship_query = f"""
        MATCH (o:OntologyNode {{label: "{label}"}})
        MATCH (o)-[:HAS_RELATIONSHIP]->(r:OntologyRelationship)-[:HAS_TARGET]->(t)
        RETURN r.label as relationship, t.label as target;
    """
    relationship_data = NB.get_data(outgoing_relationship_query)
    if relationship_data:
        for r in relationship_data:
            relationships.append((r["relationship"], "outgoing", r["target"], label),)
    incoming_relationship_query = f"""
        MATCH (o:OntologyNode {{label: "{label}"}})
        MATCH (t)-[:HAS_RELATIONSHIP]->(r:OntologyRelationship)-[:HAS_TARGET]->(o)
        RETURN r.label as relationship, t.label as target;
    """
    relationship_data = NB.get_data(incoming_relationship_query)
    if relationship_data:
        for r in relationship_data:
            relationships.append((r["relationship"], "incoming", r["target"], label),)

    if properties_data:
        property_map = {
            "HAS_PROPERTY": "allowed",
            "REQUIRE_PROPERTY": "required"
        }
        for p in properties_data:
            property_type = p["type"]
            property_label = p["property"].strip("`")
            if property_label not in properties:
                properties[property_label] = [property_map[property_type], label]

    if not subclass_data:
        return lineage, properties, relationships
    else:
        superclass_label = subclass_data[0]["label"].strip("`")
        lineage.append(superclass_label)
        return traverse_ontology(superclass_label, lineage, properties, relationships)


def handle_info(label):
    label = label.strip("`")
    lineage, properties, relationships = traverse_ontology(label, [label], dict(), list())
    print(f"Ontology info for {terminal_style.BOLD}{label}{terminal_style.RESET}")
    print("-"*50)
    print("Lineage:")
    print("    ", " ➜  ".join(lineage))
    print("\nProperties:")
    DictUtils.represent(properties, level=1, display=True, ignore_list=True)
    print("Relationships:")
    list_represent = ListUtils.represent(relationships, level=0, display=False)
    print(list_represent[2:-3])


def handler(tree):
    connection_type = {
        "require_property": "REQUIRE_PROPERTY",
        "set_property": "HAS_PROPERTY",
        "set_subclass": "SUBCLASS_OF"
    }
    data = NqlTransformer().transform(tree)
    ontology_type = data["type"]
    if ontology_type in ["node", "property", "relationship"]:
        handle_node(data)
    elif ontology_type in connection_type:
        handle_connect(data, connection_type[ontology_type])
    elif ontology_type == "set_relationship":
        handle_set_relationship(data)
    elif ontology_type == "info":
        handle_info(data["label"])

    else:
        print(f"Action not supported: {data['type']}")
