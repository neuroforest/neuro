"""
Unit tests for neuro.base.index — PluginIndex / OntologyIndex / KnowledgeIndex.
"""

import json
import uuid
from unittest.mock import patch

import pytest

from neuro.base.index import KnowledgeIndex, OntologyIndex, PluginIndex

pytestmark = pytest.mark.unit


def _write_nfx(path, *, kind, name, version="1.0", dependencies=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    nid = str(uuid.uuid4())
    doc = {
        "type": kind,
        "nid": nid,
        "version": version,
        "name": name,
    }
    if dependencies:
        doc["dependencies"] = list(dependencies)
    path.write_text(json.dumps(doc))
    return nid


@pytest.fixture(autouse=True)
def _stub_metaontology(tmp_path):
    """OntologyIndex pins `assets/ontology/metaontology.nfx`; tests provide a
    minimal fake at a temp path and patch the lookup."""
    meta_path = tmp_path / "_meta_assets" / "ontology" / "metaontology.nfx"
    meta_path.parent.mkdir(parents=True)
    meta_path.write_text(json.dumps({
        "type": "metaontology",
        "nid": str(uuid.uuid4()),
        "version": "1.0",
        "name": "Metaontology",
    }))
    with patch(
        "neuro.base.index.internal_utils.get_path",
        return_value=tmp_path / "_meta_assets",
    ):
        yield meta_path


class TestPluginIndexKindFilter:
    def test_only_matching_kind_registered(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        _write_nfx(root / "b.nfx", kind="knowledge", name="B")

        class _Idx(PluginIndex):
            KIND = "ontology"

        idx = _Idx(root)
        assert {e.name for e in idx.entries()} == {"A"}

    def test_knowledge_view(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        _write_nfx(root / "b.nfx", kind="knowledge", name="B")
        idx = KnowledgeIndex(root)
        assert {e.name for e in idx.entries()} == {"B"}

    def test_resolve_by_name(self, tmp_path):
        root = tmp_path / "plugins"
        path = root / "a.nfx"
        _write_nfx(path, kind="ontology", name="A")
        idx = OntologyIndex(root)
        assert idx.resolve("A") == path
        assert idx.resolve("a") == path  # case-insensitive


class TestOntologyIndexMetaontology:
    def test_metaontology_pinned(self, tmp_path, _stub_metaontology):
        root = tmp_path / "plugins"
        root.mkdir()
        idx = OntologyIndex(root)
        assert idx.metaontology_path == _stub_metaontology
        assert "Metaontology" in {e.name for e in idx.entries()}


class TestImplicitParent:
    def test_nested_ontology_gets_implicit_parent(self, tmp_path):
        root = tmp_path / "plugins"
        parent_nid = _write_nfx(
            root / "parent" / "parent.nfx", kind="ontology", name="Parent"
        )
        child_nid = _write_nfx(
            root / "parent" / "child" / "child.nfx", kind="ontology", name="Child"
        )
        idx = OntologyIndex(root)
        parent = next(e for e in idx.entries() if e.nid == parent_nid)
        child = next(e for e in idx.entries() if e.nid == child_nid)
        assert parent.implicit_parent_nid is None
        assert child.implicit_parent_nid == parent_nid
        assert idx.extra_deps(child_nid) == [parent_nid]
        assert idx.extra_deps(parent_nid) == []

    def test_top_level_has_no_implicit_parent(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        idx = OntologyIndex(root)
        assert all(e.implicit_parent_nid is None for e in idx.entries())

    def test_implicit_parent_via_kind_subdir(self, tmp_path):
        root = tmp_path / "plugins"
        parent_nid = _write_nfx(
            root / "parent" / "ontology" / "parent.nfx",
            kind="ontology",
            name="Parent",
        )
        child_nid = _write_nfx(
            root / "parent" / "child" / "ontology" / "child.nfx",
            kind="ontology",
            name="Child",
        )
        idx = OntologyIndex(root)
        child = next(e for e in idx.entries() if e.nid == child_nid)
        assert child.implicit_parent_nid == parent_nid
