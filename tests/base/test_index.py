"""
Unit tests for neuro.base.index — PluginIndex / OntologyIndex / KnowledgeIndex
/ NfxIndex.
"""

import json
import uuid

import pytest

from neuro.base.index import KnowledgeIndex, NfxIndex, OntologyIndex, PluginIndex

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


class TestPluginIndexKindFilter:
    def test_only_matching_kind_registered(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        _write_nfx(root / "b.nfx", kind="knowledge", name="B")

        class _Idx(PluginIndex):
            KIND = ("ontology",)

        idx = _Idx(root)
        assert {e.name for e in idx.entries()} == {"A"}

    def test_knowledge_view(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        _write_nfx(root / "b.nfx", kind="knowledge", name="B")
        idx = KnowledgeIndex(root)
        assert {e.name for e in idx.entries()} == {"B"}

    def test_nfx_index_accepts_all_types(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        _write_nfx(root / "b.nfx", kind="knowledge", name="B")
        _write_nfx(root / "m.nfx", kind="metaontology", name="M")
        idx = NfxIndex(root)
        assert {e.name for e in idx.entries()} == {"A", "B", "M"}
        assert {e.type for e in idx.entries()} == {"ontology", "knowledge", "metaontology"}

    def test_resolve_by_name(self, tmp_path):
        root = tmp_path / "plugins"
        path = root / "a.nfx"
        _write_nfx(path, kind="ontology", name="A")
        idx = OntologyIndex(root)
        assert idx.resolve("A") == path
        assert idx.resolve("a") == path  # case-insensitive


class TestOntologyIndexMetaontology:
    def test_metaontology_discovered_via_roots(self, tmp_path):
        """OntologyIndex accepts metaontology via the standard scan — its
        directory just needs to be one of the registry roots."""
        plugins_root = tmp_path / "plugins"
        plugins_root.mkdir()
        meta_dir = tmp_path / "assets" / "ontology"
        meta_path = meta_dir / "metaontology.nfx"
        meta_path.parent.mkdir(parents=True)
        meta_path.write_text(json.dumps({
            "type": "metaontology",
            "nid": str(uuid.uuid4()),
            "version": "1.0",
            "name": "Metaontology",
        }))
        idx = OntologyIndex(meta_dir, plugins_root)
        assert idx.metaontology_path == meta_path
        assert "Metaontology" in {e.name for e in idx.entries()}

    def test_metaontology_path_none_when_absent(self, tmp_path):
        idx = OntologyIndex(tmp_path)
        assert idx.metaontology_path is None


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
