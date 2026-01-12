from neuro.core.deep import NeuroObject, Moment
from neuro.base.api import NeuroBase
from neuro.base.nql.components import NqlTransformer, NqlGenerator


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
        "neuro.id": NeuroObject.generate_neuro_id(),
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


def handle_set_property(data):
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
        MATCH (o:OntologyObject {properties_string})
        MATCH (t:OntologyProperty {target_properties_string})
        OPTIONAL MATCH (o)-[e:HAS_PROPERTY]->(t)
        MERGE (o)-[r:HAS_PROPERTY]->(t)
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
        MATCH (o:OntologyObject {properties_string})
        MATCH (r:OntologyRelationship {relationship_properties_string})
        MATCH (t:OntologyObject {target_properties_string})
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


def handler(tree):
    data = NqlTransformer().transform(tree)
    if data["type"] in ["object", "property", "relationship"]:
        handle_node(data)
    elif data["type"] == "set_property":
        handle_set_property(data)
    elif data["type"] == "set_relationship":
        handle_set_relationship(data)
    else:
        print(f"Action not supported: {data['type']}")
