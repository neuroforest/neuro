from neuro.core import Node, Moment
from neuro.base import NeuroBase
from neuro.base.ontology import OntologyNodeInfo
from neuro.base.nql.components import NqlTransformer, NqlGenerator


NB: NeuroBase


def handle_node(data):
    label = data["label"].strip("`")
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
        "neuro.id": Node.generate_neuro_id(),
        "title": f".ontology {label}",
        **data["properties"]
    }
    properties_string = NqlGenerator().properties_string(properties)
    current_iso_z = Moment().to_iso_z()
    merge_query = f"""
           MERGE (o:{ontology_label} {{label: "{label}"}})
           ON CREATE SET
               o += {properties_string},
               o.created = datetime("{current_iso_z}"),
               o.modified = datetime("{current_iso_z}")
           ON MATCH SET
               o += {properties_string},
               o.modified = datetime("{current_iso_z}");
       """
    NB.run_query(merge_query)


def handle_connect(data, relationship_type):
    properties = {
        "label": data["label"].strip("`"),
        **data["properties"]
    }
    properties_string = NqlGenerator().properties_string(properties)
    target_properties = {
        "label": data["target_node"]["label"].strip("`"),
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


def handle_info(label):
    label = label.strip("`")
    try:
        info = OntologyNodeInfo(NB, label)
        info.display()
    except ValueError as e:
        print(e)


def handler(nb, tree):
    global NB
    NB = nb
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
