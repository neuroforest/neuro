"""
NFX format helpers.

Provides the `Nfx` value object (frozen dataclass mirroring the on-disk format)
plus pure read/write/validate/dependency-walk functions over it. No filesystem
discovery and no database access; callers supply any required resolution
(e.g. via `OntologyIndex` or a DB query).
"""

import json
import re
from dataclasses import dataclass, field

from neuro.core.data.str import Uuid
from neuro.utils.exceptions import NfxCycle, NfxViolation


_KEY_ORDER = ("nid", "name", "description", "version", "dependencies", "hash", "nodes", "relationships")
_NODE_KEY_ORDER = ("nid", "labels", "properties")
_REL_KEY_ORDER = ("from", "to", "type", "properties")


@dataclass(frozen=True, slots=True)
class Nfx:
    """In-memory representation of an NFX module.

    Frozen value object: construct via `from_dict` or directly; serialize via
    `to_dict`. Normalization (deep-copying nodes/rels, stripping `neuro.id`,
    dropping empty `properties`) happens at construction so the on-disk form
    is canonical without mutating caller inputs.

    `dependencies` is a tuple of `(nid, version)` pairs; the raw `"nid@ver"`
    string is reconstituted by `to_dict`.
    """

    nid: str = ""
    name: str = ""
    description: str = ""
    version: str = ""
    dependencies: tuple[tuple[str, str], ...] = ()
    hash: str = ""
    nodes: tuple[dict, ...] = field(default_factory=tuple)
    relationships: tuple[dict, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict) -> "Nfx":
        """Parse an NFX-shaped dict into an `Nfx`. Raises `NfxViolation` on
        malformed `nid` or `dependencies` entries.

        Strict on structural identity (top-level `nid`, dep `"nid@ver"` form);
        permissive on node/relationship payloads — `validate()` reports those.
        """
        nid = data.get("nid", "")
        if nid and not Uuid.is_valid_uuid_v4(nid):
            raise NfxViolation(f"invalid nid {nid!r} (not UUID v4)")
        deps: list[tuple[str, str]] = []
        for raw in data.get("dependencies", []) or []:
            if not isinstance(raw, str) or "@" not in raw:
                raise NfxViolation(f"dependency {raw!r} not in 'nid@version' form")
            d_nid, _, d_ver = raw.rpartition("@")
            if not Uuid.is_valid_uuid_v4(d_nid):
                raise NfxViolation(f"dependency nid {d_nid!r} not UUID v4")
            if not d_ver:
                raise NfxViolation(f"dependency {raw!r} has empty version")
            deps.append((d_nid, d_ver))
        nodes: list[dict] = []
        for n in data.get("nodes", []) or []:
            n = dict(n)
            props = dict(n.get("properties", {}) or {})
            props.pop("neuro.id", None)
            if props:
                n["properties"] = props
            else:
                n.pop("properties", None)
            nodes.append(n)
        relationships: list[dict] = []
        for r in data.get("relationships", []) or []:
            r = dict(r)
            if not r.get("properties"):
                r.pop("properties", None)
            relationships.append(r)
        return cls(
            nid=nid,
            name=data.get("name", "") or "",
            description=data.get("description", "") or "",
            version=data.get("version", "") or "",
            dependencies=tuple(deps),
            hash=data.get("hash", "") or "",
            nodes=tuple(nodes),
            relationships=tuple(relationships),
        )

    def to_dict(self) -> dict:
        """Serialize to a canonical NFX dict in `_KEY_ORDER`. Empty optional
        fields (`name`, `description`, `version`, `dependencies`, `hash`, and
        `nid` if blank) are omitted; `nodes` and `relationships` are always
        present (even if empty) to match historical writer behavior.
        """
        out: dict = {}
        if self.nid:
            out["nid"] = self.nid
        if self.name:
            out["name"] = self.name
        if self.description:
            out["description"] = self.description
        if self.version:
            out["version"] = self.version
        if self.dependencies:
            out["dependencies"] = [f"{n}@{v}" for n, v in self.dependencies]
        if self.hash:
            out["hash"] = self.hash
        out["nodes"] = [dict(n) for n in self.nodes]
        out["relationships"] = [dict(r) for r in self.relationships]
        return out

    @property
    def node_nids(self) -> frozenset[str]:
        """Frozenset of nids of locally declared nodes."""
        return frozenset(n["nid"] for n in self.nodes if "nid" in n)

    @property
    def dep_nids(self) -> tuple[str, ...]:
        """Direct dependency nids, version-stripped, in declaration order."""
        return tuple(n for n, _ in self.dependencies)


def _check_keys(keys, canonical):
    """Return (unknown, out_of_order) given actual `keys` vs `canonical` tuple.

    - `unknown` is the list of keys not in `canonical` (preserving encounter order).
    - `out_of_order` is True if the known keys do not appear in canonical order.
    Not every canonical key must be present.
    """
    canonical_set = set(canonical)
    unknown = [k for k in keys if k not in canonical_set]
    known = [k for k in keys if k in canonical_set]
    expected = [k for k in canonical if k in set(known)]
    return unknown, known != expected


def read(path) -> Nfx:
    """Read an NFX file and return its parsed `Nfx`."""
    with open(path) as f:
        return Nfx.from_dict(json.load(f))


def dumps(doc: Nfx) -> str:
    """Serialize `Nfx` to canonical on-disk text.

    4-space indentation with `"labels"` arrays re-inlined to one line,
    matching the repo convention and the pre-commit lint rule.
    """
    text = json.dumps(doc.to_dict(), indent=4, default=str)
    text = re.sub(
        r'"labels":\s*\[\s*\n([^\]]*?)\n\s*\]',
        lambda m: '"labels": ['
        + ", ".join(part.strip().rstrip(",") for part in m.group(1).splitlines())
        + "]",
        text,
    )
    return text + "\n"


def write(path, doc: Nfx) -> None:
    """Write an `Nfx` to disk in canonical form."""
    with open(path, "w") as f:
        f.write(dumps(doc))


def validate(doc: Nfx, dependency_nids: set[str] | None = None) -> dict:
    """Validate referential integrity of an `Nfx`.

    `dependency_nids` should include nids reachable through direct AND transitive
    dependencies — see `dependency_node_nids()` for a helper that walks the graph.

    Returns dict with 'unresolved' (endpoints not in local or dependency nodes),
    'foreign' (both endpoints are non-local), and 'invalid_nids' (not valid UUID v4).
    Format-level checks (key order / unknown keys on the raw on-disk dict) live
    in `lint_format()`.
    """
    local_nids = doc.node_nids
    valid_nids = set(local_nids) | (dependency_nids or set())

    all_nids: set[str] = set(local_nids)
    for rel in doc.relationships:
        all_nids.add(rel["from"])
        all_nids.add(rel["to"])
    invalid_nids = sorted(nid for nid in all_nids if not Uuid.is_valid_uuid_v4(nid))

    unresolved = []
    foreign = []
    for rel in doc.relationships:
        from_nid, to_nid = rel["from"], rel["to"]
        if from_nid not in valid_nids or to_nid not in valid_nids:
            unresolved.append(rel)
        elif from_nid not in local_nids and to_nid not in local_nids:
            foreign.append(rel)

    return {
        "unresolved": unresolved,
        "foreign": foreign,
        "invalid_nids": invalid_nids,
    }


def lint_format(data: dict) -> dict:
    """Inspect a raw NFX dict for format-level issues.

    Operates on the unparsed dict (pre-`Nfx.from_dict`) because once parsed,
    unknown keys and key-order information are lost. Returns 'unknown_keys'
    (keys outside the canonical schema) and 'key_order' (places where present
    keys are not in canonical order).
    """
    unknown_keys: list[dict] = []
    key_order: list[dict] = []

    def _inspect(keys, canonical, where):
        unknown, bad_order = _check_keys(keys, canonical)
        if unknown:
            unknown_keys.append({"where": where, "keys": unknown})
        if bad_order:
            key_order.append({"where": where, "keys": list(keys)})

    _inspect(list(data.keys()), _KEY_ORDER, "top-level")
    for i, n in enumerate(data.get("nodes", [])):
        _inspect(list(n.keys()), _NODE_KEY_ORDER, f"nodes[{i}]")
    for i, r in enumerate(data.get("relationships", [])):
        _inspect(list(r.keys()), _REL_KEY_ORDER, f"relationships[{i}]")

    return {"unknown_keys": unknown_keys, "key_order": key_order}


def dependency_node_nids(doc: Nfx, resolve) -> set[str]:
    """Collect nids of all nodes defined by direct and transitive dependencies.

    `resolve(nid)` returns the `Nfx` for a dependency, or None if the dependency
    is unavailable (its nodes are then simply absent from the result).

    Raises `NfxCycle(cycle_path)` if the dependency graph contains a cycle,
    where `cycle_path` is the list of dep nids traversed (e.g. [A, B, A]).
    """
    collected: set[str] = set()
    DONE, IN_PATH = 1, 2
    state: dict[str, int] = {}

    def walk(nid, path):
        marker = state.get(nid)
        if marker == IN_PATH:
            raise NfxCycle(path[path.index(nid):] + [nid])
        if marker == DONE:
            return
        state[nid] = IN_PATH
        dep_doc = resolve(nid)
        if dep_doc is not None:
            collected.update(dep_doc.node_nids)
            for d_nid in dep_doc.dep_nids:
                walk(d_nid, path + [nid])
        state[nid] = DONE

    for d_nid in doc.dep_nids:
        walk(d_nid, [])
    return collected
