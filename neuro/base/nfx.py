"""
NFX format I/O — pure read/write, no database, no validation.
"""

import json


def read(path):
    """Read an NFX file and return {"nodes": [...], "relationships": [...]}."""
    with open(path) as f:
        return json.load(f)


def write(path, nodes, relationships):
    """Write nodes and relationships to an NFX file.

    Strips `neuro.id` from node properties (it's stored as `nid`).
    """
    for n in nodes:
        n["properties"].pop("neuro.id", None)

    data = {"nodes": nodes, "relationships": relationships}
    with open(path, "w") as f:
        json.dump(data, f, default=str)

    return data
