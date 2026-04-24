"""
NFX format helpers — pure functions over NFX-shaped dicts.

Covers read/write, referential-integrity validation, and dependency-graph
traversal. No filesystem discovery and no database access; callers supply
any required resolution (e.g. via `OntologyIndex` or a DB query).
"""

import json
import re

from neuro.core.data.str import Uuid
from neuro.utils.exceptions import NfxCycle


_KEY_ORDER = ("nid", "name", "description", "version", "dependencies", "hash", "nodes", "relationships")


def _reorder(data: dict) -> dict:
    """Return a new dict with canonical top-level key ordering; unknown keys keep their original order at the end."""
    out = {k: data[k] for k in _KEY_ORDER if k in data}
    for k, v in data.items():
        if k not in out:
            out[k] = v
    return out


def dumps(data: dict) -> str:
    """Serialize NFX data to the canonical on-disk format.

    4-space indentation with `"labels"` arrays re-inlined to one line,
    matching the repo convention and the pre-commit lint rule.
    """
    text = json.dumps(_reorder(data), indent=4, default=str)
    text = re.sub(
        r'"labels":\s*\[\s*\n([^\]]*?)\n\s*\]',
        lambda m: '"labels": ['
        + ", ".join(part.strip().rstrip(",") for part in m.group(1).splitlines())
        + "]",
        text,
    )
    return text + "\n"


def validate(data, dependency_nids=None):
    """Validate NFX referential integrity and jurisdiction.

    `dependency_nids` should include nids reachable through direct AND transitive
    dependencies — see `dependency_node_nids()` for a helper that walks the graph.

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


def dependency_node_nids(data, resolve):
    """Collect nids of all nodes defined by direct and transitive dependencies.

    `resolve(nid)` returns the NFX data dict for a dependency, or None if the
    dependency is unavailable (its nodes are then simply absent from the result).

    Raises `NfxCycle(cycle_path)` if the dependency graph contains a cycle,
    where `cycle_path` is the list of dep nids traversed (e.g. [A, B, A]).
    """
    collected = set()
    DONE, IN_PATH = 1, 2
    state: dict[str, int] = {}

    def walk(nid, path):
        marker = state.get(nid)
        if marker == IN_PATH:
            raise NfxCycle(path[path.index(nid):] + [nid])
        if marker == DONE:
            return
        state[nid] = IN_PATH
        dep_data = resolve(nid)
        if dep_data is not None:
            collected.update(n["nid"] for n in dep_data.get("nodes", []))
            for dep in dep_data.get("dependencies", []):
                walk(dep.partition("@")[0], path + [nid])
        state[nid] = DONE

    for dep in data.get("dependencies", []):
        walk(dep.partition("@")[0], [])
    return collected


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
    data = _reorder(data)
    with open(path, "w") as f:
        json.dump(data, f, default=str)

    return data
