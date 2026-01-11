from neuro.core.deep import NeuroObject, Moment
from neuro.base.api import NeuroBase
from neuro.base.nql.components import NqlTransformer, NqlGenerator


def handler(tree):
    nb = NeuroBase()
    data = NqlTransformer().transform(tree)
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

    match_data = nb.get_data(match_query, parameters={
        "properties": properties
    })
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
    nb.run_query(merge_query)
