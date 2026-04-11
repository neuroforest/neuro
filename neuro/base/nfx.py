"""
NFX format I/O — pure read/write, no database, no validation.
"""

import json

from neuro.core.data.str import Uuid


def validate(data, dependency_nids=None):
    """Validate NFX referential integrity and jurisdiction.

    Returns dict with 'unresolved' (endpoints not in local or dependency nodes),
    'foreign' (both endpoints are non-local), and 'invalid_nids' (not valid UUID v4).
    """
    local_nids = {n["nid"] for n in data.get("nodes", [])}
    valid_nids = local_nids | (dependency_nids or set())

    all_nids = {n["nid"] for n in data.get("nodes", [])}
    for rel in data.get("relationships", []):
        all_nids.add(rel["from"])
        all_nids.add(rel["to"])
    invalid_nids = sorted(nid for nid in all_nids if not Uuid.is_valid_uuid_v4(nid))

    unresolved = []
    foreign = []
    for rel in data.get("relationships", []):
        from_nid, to_nid = rel["from"], rel["to"]
        if from_nid not in valid_nids or to_nid not in valid_nids:
            unresolved.append(rel)
        elif from_nid not in local_nids and to_nid not in local_nids:
            foreign.append(rel)
    return {"unresolved": unresolved, "foreign": foreign, "invalid_nids": invalid_nids}


def read(path):
    """Read an NFX file and return its full contents as a dict."""
    with open(path) as f:
        return json.load(f)


def write(path, nodes, relationships, nid="", name="", description="", version="",
          dependencies=None):
    """Write nodes and relationships to an NFX file.

    Strips `neuro.id` from node properties (it is stored as top-level `nid` on each node).
    Omits empty `properties` dicts and empty relationship `properties`.
    """
    for n in nodes:
        n["properties"].pop("neuro.id", None)
        if not n["properties"]:
            del n["properties"]

    for r in relationships:
        if not r.get("properties"):
            r.pop("properties", None)

    data = {}
    if nid:
        data["nid"] = nid
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
