"""
Unit tests for neuro.base.index - PluginIndex / OntologyIndex / KnowledgeIndex
/ NfxIndex.
"""

import json
import uuid

import pytest

from neuro.base.index import KnowledgeIndex, NfxIndex, OntologyIndex, PluginIndex
from neuro.utils import exceptions

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
        """OntologyIndex accepts metaontology via the standard scan - its
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


class TestConsolidatedRoot:
    def test_indexes_both_kinds(self, tmp_path):
        root = tmp_path / ".nf"
        a = _write_nfx(root / "ontology" / "A.nfx", kind="ontology", name="A")
        k = _write_nfx(root / "knowledge" / "K.nfx", kind="knowledge", name="K")
        idx = NfxIndex(root)
        by_nid = {e.nid: e for e in idx.entries()}
        assert set(by_nid) == {a, k}
        assert by_nid[a].registry_root == root.resolve()
        assert by_nid[a].validators_path == (root / "validators" / "A.py").resolve()
        assert by_nid[a].local_name == "A"
        assert by_nid[k].plugin_root is None
        assert idx.roots == (root.resolve(),)

    def test_subdir_type_mismatch_fatal(self, tmp_path):
        root = tmp_path / ".nf"
        _write_nfx(root / "ontology" / "A.nfx", kind="knowledge", name="A")
        with pytest.raises(exceptions.NfxViolation, match="ontology/"):
            NfxIndex(root)

    def test_local_name_collision_in_root_fatal(self, tmp_path):
        root = tmp_path / ".nf"
        _write_nfx(root / "ontology" / "A.nfx", kind="ontology", name="A")
        _write_nfx(root / "knowledge" / "a.nfx", kind="knowledge", name="a")
        with pytest.raises(exceptions.NfxViolation, match="local name collision"):
            NfxIndex(root)

    def test_local_name_may_repeat_across_roots(self, tmp_path):
        r1 = tmp_path / "one" / ".nf"
        r2 = tmp_path / "two" / ".nf"
        _write_nfx(r1 / "ontology" / "A.nfx", kind="ontology", name="A")
        _write_nfx(r2 / "ontology" / "A.nfx", kind="ontology", name="A")
        idx = NfxIndex(r1, r2)
        assert len(idx.entries()) == 2

    def test_nid_collision_across_roots_fatal(self, tmp_path):
        r1 = tmp_path / "one" / ".nf"
        r2 = tmp_path / "plugins"
        nid = _write_nfx(r1 / "ontology" / "A.nfx", kind="ontology", name="A")
        (r2).mkdir()
        (r2 / "b.nfx").write_text(json.dumps({"type": "ontology", "nid": nid, "version": "1.0", "name": "B"}))
        with pytest.raises(exceptions.NfxViolation, match="nid collision"):
            NfxIndex(r1, r2)

    def test_validators_loaded_from_validators_dir(self, tmp_path):
        import sys
        from neuro.base import plugins
        root = tmp_path / ".nf"
        _write_nfx(root / "ontology" / "A.nfx", kind="ontology", name="A")
        (root / "validators").mkdir()
        (root / "validators" / "A.py").write_text(
            "from neuro.base.plugins import register\n"
            "register('NfTestType', lambda v, _mp: v == 'ok')\n"
        )
        try:
            OntologyIndex(root)
            assert plugins.lookup("NfTestType")("ok", None) is True
        finally:
            plugins.clear()
            for name in [n for n in sys.modules if n.startswith("neuro._plugins.")]:
                del sys.modules[name]


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
