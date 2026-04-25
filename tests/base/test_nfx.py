"""
Unit tests for neuro.base.nfx — Nfx value object + free functions.
"""

import uuid

import pytest

pytestmark = pytest.mark.unit

LOCAL_1 = str(uuid.uuid4())
LOCAL_2 = str(uuid.uuid4())
DEP_1 = str(uuid.uuid4())
DEP_2 = str(uuid.uuid4())
DIRECT_NID = str(uuid.uuid4())
TRANSITIVE_NID = str(uuid.uuid4())
DIRECT_NODE = str(uuid.uuid4())
TRANSITIVE_NODE = str(uuid.uuid4())


# --- Nfx value object ---

def test_nfx_from_dict_parses_dependencies():
    from neuro.base.nfx import Nfx
    doc = Nfx.from_dict({
        "nid": LOCAL_1,
        "name": "X",
        "version": "1.0",
        "dependencies": [f"{DEP_1}@1.2", f"{DEP_2}@3.4"],
        "nodes": [{"nid": LOCAL_2}],
        "relationships": [],
    })
    assert doc.dependencies == ((DEP_1, "1.2"), (DEP_2, "3.4"))
    assert doc.dep_nids == (DEP_1, DEP_2)
    assert doc.node_nids == frozenset({LOCAL_2})


def test_nfx_from_dict_rejects_invalid_nid():
    from neuro.base.nfx import Nfx
    from neuro.utils.exceptions import NfxViolation
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"nid": "not-a-uuid"})


def test_nfx_from_dict_rejects_malformed_dep():
    from neuro.base.nfx import Nfx
    from neuro.utils.exceptions import NfxViolation
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"dependencies": ["no-version-here"]})
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"dependencies": [f"{DEP_1}@"]})
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"dependencies": ["bad-nid@1.0"]})


def test_nfx_from_dict_normalizes_nodes():
    """neuro.id stripped from properties; empty properties dropped; caller's input untouched."""
    from neuro.base.nfx import Nfx
    src_node = {"nid": LOCAL_1, "labels": ["L"], "properties": {"neuro.id": "x", "k": 1}}
    src_empty = {"nid": LOCAL_2, "labels": ["L"], "properties": {"neuro.id": "y"}}
    src_data = {"nodes": [src_node, src_empty], "relationships": []}
    doc = Nfx.from_dict(src_data)
    assert doc.nodes[0]["properties"] == {"k": 1}
    assert "properties" not in doc.nodes[1]
    # caller input untouched
    assert "neuro.id" in src_node["properties"]
    assert "neuro.id" in src_empty["properties"]


def test_nfx_from_dict_normalizes_relationships():
    from neuro.base.nfx import Nfx
    doc = Nfx.from_dict({
        "relationships": [
            {"from": LOCAL_1, "to": LOCAL_2, "type": "USES", "properties": {}},
            {"from": LOCAL_1, "to": LOCAL_2, "type": "OTHER"},
        ],
    })
    assert "properties" not in doc.relationships[0]
    assert "properties" not in doc.relationships[1]


def test_nfx_to_dict_omits_empty_optionals_and_roundtrips():
    from neuro.base.nfx import Nfx
    src = {
        "nid": LOCAL_1,
        "name": "X",
        "version": "1.0",
        "dependencies": [f"{DEP_1}@1.0"],
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"k": 1}}],
        "relationships": [{"from": LOCAL_2, "to": LOCAL_2, "type": "SELF"}],
    }
    out = Nfx.from_dict(src).to_dict()
    assert out["dependencies"] == [f"{DEP_1}@1.0"]
    assert "description" not in out and "hash" not in out
    assert out["nodes"] and out["relationships"]
    # roundtrip stability
    assert Nfx.from_dict(out).to_dict() == out


def test_nfx_to_dict_includes_nodes_and_relationships_even_when_empty():
    from neuro.base.nfx import Nfx
    out = Nfx(nid=LOCAL_1).to_dict()
    assert out == {"nid": LOCAL_1, "nodes": [], "relationships": []}


def test_nfx_is_frozen():
    from neuro.base.nfx import Nfx
    doc = Nfx(nid=LOCAL_1)
    with pytest.raises(Exception):
        doc.nid = LOCAL_2  # frozen dataclass


def test_nfx_hash_field_roundtrip():
    from neuro.base.nfx import Nfx
    doc = Nfx.from_dict({"nid": LOCAL_1, "hash": "abc123", "nodes": [], "relationships": []})
    assert doc.hash == "abc123"
    assert doc.to_dict()["hash"] == "abc123"


# --- validate (referential integrity) ---

def test_validate_foreign_relationship():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}],
        "relationships": [
            {"from": LOCAL_1, "to": DEP_1, "type": "USES"},
            {"from": DEP_1, "to": DEP_2, "type": "RELATES"},
        ],
    })
    result = validate(doc, dependency_nids={DEP_1, DEP_2})
    assert len(result["foreign"]) == 1
    assert result["foreign"][0]["type"] == "RELATES"
    assert result["unresolved"] == []
    assert result["invalid_nids"] == []


def test_validate_unresolved_relationship():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": "unknown", "type": "RELATES"}],
    })
    result = validate(doc)
    assert len(result["unresolved"]) == 1
    assert result["foreign"] == []
    assert result["invalid_nids"] == ["unknown"]


def test_validate_invalid_nid():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [
            {"nid": "not-a-uuid"},
            {"nid": "550e8400-e29b-41d4-a716-446655440000"},
        ],
        "relationships": [],
    })
    result = validate(doc)
    assert result["invalid_nids"] == ["not-a-uuid"]


def test_validate_accepts_transitive_endpoint():
    """A relationship from a local node to a transitive-dep node validates."""
    from neuro.base.nfx import Nfx, dependency_node_nids, validate
    registry = {
        DIRECT_NID: Nfx.from_dict({
            "nodes": [{"nid": DIRECT_NODE}],
            "dependencies": [f"{TRANSITIVE_NID}@1.0"],
        }),
        TRANSITIVE_NID: Nfx.from_dict({
            "nodes": [{"nid": TRANSITIVE_NODE}],
            "dependencies": [],
        }),
    }
    doc = Nfx.from_dict({
        "dependencies": [f"{DIRECT_NID}@1.0"],
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": TRANSITIVE_NODE, "type": "USES"}],
    })
    result = validate(doc, dependency_nids=dependency_node_nids(doc, registry.get))
    assert result["unresolved"] == []
    assert result["foreign"] == []


# --- dependency_node_nids (transitive walk) ---

def test_dependency_node_nids_transitive():
    """dependency_node_nids walks direct + transitive deps."""
    from neuro.base.nfx import Nfx, dependency_node_nids
    registry = {
        DIRECT_NID: Nfx.from_dict({
            "nodes": [{"nid": DIRECT_NODE}],
            "dependencies": [f"{TRANSITIVE_NID}@1.0"],
        }),
        TRANSITIVE_NID: Nfx.from_dict({
            "nodes": [{"nid": TRANSITIVE_NODE}],
            "dependencies": [],
        }),
    }
    doc = Nfx.from_dict({"dependencies": [f"{DIRECT_NID}@1.0"]})
    nids = dependency_node_nids(doc, registry.get)
    assert nids == {DIRECT_NODE, TRANSITIVE_NODE}


def test_dependency_node_nids_rejects_cycle():
    """Cyclic dependency graphs are rejected with a cycle path."""
    from neuro.base.nfx import Nfx, dependency_node_nids
    from neuro.utils.exceptions import NfxCycle
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    registry = {
        a: Nfx.from_dict({"nodes": [], "dependencies": [f"{b}@1.0"]}),
        b: Nfx.from_dict({"nodes": [], "dependencies": [f"{a}@1.0"]}),
    }
    doc = Nfx.from_dict({"dependencies": [f"{a}@1.0"]})
    with pytest.raises(NfxCycle) as exc:
        dependency_node_nids(doc, registry.get)
    assert exc.value.args[0][0] == exc.value.args[0][-1]


def test_dependency_node_nids_missing_resolve():
    """Unresolvable deps are silently skipped (validate() will flag unresolved rels)."""
    from neuro.base.nfx import Nfx, dependency_node_nids
    doc = Nfx.from_dict({"dependencies": [f"{DEP_1}@1.0"]})
    assert dependency_node_nids(doc, lambda _nid: None) == set()


# --- lint_format (raw-dict format checks) ---

def test_lint_format_key_order_top_level():
    from neuro.base.nfx import lint_format
    data = {"nid": LOCAL_1, "nodes": [], "version": "1.0", "relationships": []}
    result = lint_format(data)
    assert len(result["key_order"]) == 1
    assert result["key_order"][0]["where"] == "top-level"
    assert result["unknown_keys"] == []


def test_lint_format_key_order_node():
    from neuro.base.nfx import lint_format
    data = {
        "nodes": [{"labels": ["X"], "nid": LOCAL_1}],
        "relationships": [],
    }
    result = lint_format(data)
    assert len(result["key_order"]) == 1
    assert result["key_order"][0]["where"] == "nodes[0]"


def test_lint_format_key_order_relationship():
    from neuro.base.nfx import lint_format
    data = {
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}],
        "relationships": [{"to": LOCAL_2, "from": LOCAL_1, "type": "USES"}],
    }
    result = lint_format(data)
    assert len(result["key_order"]) == 1
    assert result["key_order"][0]["where"] == "relationships[0]"


def test_lint_format_unknown_key_top_level():
    from neuro.base.nfx import lint_format
    data = {"nid": LOCAL_1, "bogus": 1, "nodes": [], "relationships": []}
    result = lint_format(data)
    assert result["unknown_keys"] == [{"where": "top-level", "keys": ["bogus"]}]


def test_lint_format_unknown_key_node():
    from neuro.base.nfx import lint_format
    data = {
        "nodes": [{"nid": LOCAL_1, "labels": ["X"], "extra": 1}],
        "relationships": [],
    }
    result = lint_format(data)
    assert result["unknown_keys"] == [{"where": "nodes[0]", "keys": ["extra"]}]


def test_lint_format_accepts_canonical_key_order():
    from neuro.base.nfx import lint_format
    data = {
        "nid": LOCAL_1,
        "name": "X",
        "version": "1.0",
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"a": 1}}],
        "relationships": [{"from": LOCAL_2, "to": LOCAL_2, "type": "SELF"}],
    }
    result = lint_format(data)
    assert result["key_order"] == []
    assert result["unknown_keys"] == []


# --- read / write roundtrip ---

def test_read_write_roundtrip(tmp_path):
    from neuro.base.nfx import Nfx, read, write
    src = Nfx.from_dict({
        "nid": LOCAL_1,
        "name": "Test",
        "version": "1.0",
        "dependencies": [f"{DEP_1}@1.0"],
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"k": 1}}],
        "relationships": [{"from": LOCAL_2, "to": LOCAL_2, "type": "SELF"}],
    })
    p = tmp_path / "x.nfx"
    write(p, src)
    assert read(p) == src
