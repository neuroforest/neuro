from neuro.core import Node, Moment
from neuro.base.api import NeuroBase
from neuro.base.api.ontology import NodeOntology
from neuro.base.nql.components import NqlTransformer, NqlGenerator
from neuro.core.data.dict import DictUtils
from neuro.core.data.list import ListUtils
from neuro.utils import terminal_style


NB: NeuroBase


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


def handle_info(label):
    label = label.strip("`")
    node_ontology = NodeOntology(NB, label)
    print(f"Ontology info for {terminal_style.BOLD}{label}{terminal_style.RESET}")
    print("-"*50)
    print("Lineage:")
    print("    ", " ➜  ".join(node_ontology.lineage))
    print("\nProperties:")
    DictUtils.represent(node_ontology.properties, level=1, display=True, ignore_list=True)
    print("Relationships:")
    list_represent = ListUtils.represent(node_ontology.relationships, level=0, display=False)
    print(list_represent[2:-3])


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
