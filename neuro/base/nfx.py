"""
NFX format I/O — pure read/write, no database, no validation.
"""

import json


def read(path):
    """Read an NFX file and return {"nodes": [...], "relationships": [...]}."""
    with open(path) as f:
        return json.load(f)


def write(path, nodes, relationships, name="", description="", version="",
          dependencies=None):
    """Write nodes and relationships to an NFX file.

    Strips `neuro.id` from node properties (it's stored as `nid`).
    """
    for n in nodes:
        n["properties"].pop("neuro.id", None)
        if not n["properties"]:
            del n["properties"]

    for r in relationships:
        if not r.get("properties"):
            r.pop("properties", None)

    data = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if version:
        data["version"] = version
    if dependencies:
        data["dependencies"] = dependencies
    data["nodes"] = nodes
    data["relationships"] = relationships
    with open(path, "w") as f:
        json.dump(data, f, default=str)

    return data
