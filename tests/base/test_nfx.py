"""
Unit tests for neuro.base.nfx — NFX validation.
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


def test_validate_foreign_relationship():
    from neuro.base.nfx import validate
    data = {
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}],
        "relationships": [
            {"from": LOCAL_1, "to": DEP_1, "type": "USES"},
            {"from": DEP_1, "to": DEP_2, "type": "RELATES"},
        ],
    }
    result = validate(data, dependency_nids={DEP_1, DEP_2})
    assert len(result["foreign"]) == 1
    assert result["foreign"][0]["type"] == "RELATES"
    assert result["unresolved"] == []
    assert result["invalid_nids"] == []


def test_validate_unresolved_relationship():
    from neuro.base.nfx import validate
    data = {
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": "unknown", "type": "RELATES"}],
    }
    result = validate(data)
    assert len(result["unresolved"]) == 1
    assert result["foreign"] == []
    assert result["invalid_nids"] == ["unknown"]


def test_validate_invalid_nid():
    from neuro.base.nfx import validate
    data = {
        "nodes": [
            {"nid": "not-a-uuid"},
            {"nid": "550e8400-e29b-41d4-a716-446655440000"},
        ],
        "relationships": [],
    }
    result = validate(data)
    assert result["invalid_nids"] == ["not-a-uuid"]


def test_dependency_node_nids_transitive():
    """dependency_node_nids walks direct + transitive deps."""
    from neuro.base.nfx import dependency_node_nids
    registry = {
        DIRECT_NID: {
            "nodes": [{"nid": DIRECT_NODE}],
            "dependencies": [f"{TRANSITIVE_NID}@1.0"],
        },
        TRANSITIVE_NID: {
            "nodes": [{"nid": TRANSITIVE_NODE}],
            "dependencies": [],
        },
    }
    data = {"dependencies": [f"{DIRECT_NID}@1.0"]}
    nids = dependency_node_nids(data, registry.get)
    assert nids == {DIRECT_NODE, TRANSITIVE_NODE}


def test_dependency_node_nids_rejects_cycle():
    """Cyclic dependency graphs are rejected with a cycle path."""
    from neuro.base.nfx import dependency_node_nids
    from neuro.utils.exceptions import NfxCycle
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    registry = {
        a: {"nodes": [], "dependencies": [f"{b}@1.0"]},
        b: {"nodes": [], "dependencies": [f"{a}@1.0"]},
    }
    data = {"dependencies": [f"{a}@1.0"]}
    with pytest.raises(NfxCycle) as exc:
        dependency_node_nids(data, registry.get)
    assert exc.value.args[0][0] == exc.value.args[0][-1]


def test_dependency_node_nids_missing_resolve():
    """Unresolvable deps are silently skipped (validate() will flag unresolved rels)."""
    from neuro.base.nfx import dependency_node_nids
    data = {"dependencies": [f"{DEP_1}@1.0"]}
    assert dependency_node_nids(data, lambda _nid: None) == set()


def test_validate_accepts_transitive_endpoint():
    """A relationship from a local node to a transitive-dep node validates."""
    from neuro.base.nfx import dependency_node_nids, validate
    registry = {
        DIRECT_NID: {
            "nodes": [{"nid": DIRECT_NODE}],
            "dependencies": [f"{TRANSITIVE_NID}@1.0"],
        },
        TRANSITIVE_NID: {
            "nodes": [{"nid": TRANSITIVE_NODE}],
            "dependencies": [],
        },
    }
    data = {
        "dependencies": [f"{DIRECT_NID}@1.0"],
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": TRANSITIVE_NODE, "type": "USES"}],
    }
    result = validate(data, dependency_nids=dependency_node_nids(data, registry.get))
    assert result["unresolved"] == []
    assert result["foreign"] == []
