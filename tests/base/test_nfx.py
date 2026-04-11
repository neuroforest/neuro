"""
Unit tests for neuro.base.nfx — NFX validation.
"""

import uuid

import pytest

from neuro.base.nfx import validate

pytestmark = pytest.mark.unit

LOCAL_1 = str(uuid.uuid4())
LOCAL_2 = str(uuid.uuid4())
DEP_1 = str(uuid.uuid4())
DEP_2 = str(uuid.uuid4())


def test_validate_foreign_relationship():
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
    data = {
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": "unknown", "type": "RELATES"}],
    }
    result = validate(data)
    assert len(result["unresolved"]) == 1
    assert result["foreign"] == []
    assert result["invalid_nids"] == ["unknown"]


def test_validate_invalid_nid():
    data = {
        "nodes": [
            {"nid": "not-a-uuid"},
            {"nid": "550e8400-e29b-41d4-a716-446655440000"},
        ],
        "relationships": [],
    }
    result = validate(data)
    assert result["invalid_nids"] == ["not-a-uuid"]
