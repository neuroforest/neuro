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

    def test_qualified(self, tmp_path):
        from neuro.base import nfx

        trees = {}
        for token, stems in (("", ("social", "time")), ("side", ("social", "git"))):
            root = tmp_path / (token or "home") / ".nf"
            root.mkdir(parents=True)
            nfx.write(root / nfx.NAMESPACE_FILENAME, nfx.Nfx(type=nfx.NAMESPACE_TYPE, nid=str(uuid.uuid4()),
                                                            version="1.0", name=token or "Root", namespace=token))
            for stem in stems:
                _write_nfx(root / "ontology" / f"{stem}.nfx", kind="ontology", name=stem)
            trees[token] = root
        idx = NfxIndex(*trees.values())
        # a stem is unique in its tree only: across trees a module is `<namespace>-<stem>`
        assert idx.resolve("git") == trees["side"] / "ontology" / "git.nfx" == idx.resolve("side-git")
        assert idx.resolve("root-social") == trees[""] / "ontology" / "social.nfx"
        assert idx.resolve("side-social") == trees["side"] / "ontology" / "social.nfx"
        with pytest.raises(exceptions.AmbiguousModule) as e:
            idx.resolve("social")
        assert e.value.candidates == ["root-social", "side-social"]
        assert idx.resolve("nope") is None
        assert [idx.qualified(m) for m in idx.suggest("soc")] == ["root-social", "side-social"]
        assert [idx.qualified(m) for m in idx.suggest("side-")] == ["side-git", "side-social"]


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


def _write_namespace(root, token, *, name="Root", nid=None, was=(), dependencies=(), type_="namespace"):
    root.mkdir(parents=True, exist_ok=True)
    nid = nid or str(uuid.uuid4())
    doc = {"type": type_, "nid": nid, "version": "1.0", "name": name, "namespace": token}
    if was:
        doc["was"] = list(was)
    doc["dependencies"] = list(dependencies)
    (root / "namespace.nfx").write_text(json.dumps(doc))
    return nid


class TestNamespace:
    def test_read_namespaces(self, tmp_path):
        nf = tmp_path / "app" / ".nf"
        home = tmp_path / "home" / ".nf"
        nf_nid = _write_namespace(nf, "nf", name="Builtin")
        root_nid = _write_namespace(home, "", was=("old",), dependencies=[f"{nf_nid}@1.0"])
        a = _write_nfx(nf / "ontology" / "A.nfx", kind="ontology", name="A")
        k = _write_nfx(home / "knowledge" / "K.nfx", kind="knowledge", name="K")
        idx = NfxIndex(nf, home)
        by_nid = {e.nid: e for e in idx.entries()}
        assert set(by_nid) == {a, k}
        assert (by_nid[a].namespace, by_nid[a].namespace_nid) == ("nf", nf_nid)
        assert (by_nid[k].namespace, by_nid[k].namespace_nid) == ("", root_nid)
        tokens = [ns.token for ns in idx.namespaces()]
        assert tokens == ["nf", ""]
        home_ns = idx.namespace_of(home)
        assert home_ns.name == "Root" and home_ns.was == ("old",)
        assert home_ns.dependencies == ((nf_nid, "1.0"),)
        assert home_ns.path == (home / "namespace.nfx").resolve()

    def test_missing_declaration_warns(self, tmp_path, caplog):
        root = tmp_path / ".nf"
        a = _write_nfx(root / "ontology" / "A.nfx", kind="ontology", name="A")
        idx = NfxIndex(root)
        entry = idx.entries()[0]
        assert entry.nid == a and entry.namespace is None and entry.namespace_nid is None
        assert idx.namespace_of(root) is None and idx.namespaces() == []
        assert "namespace.nfx" in caplog.text

    def test_legacy_root_has_none(self, tmp_path):
        root = tmp_path / "plugins"
        _write_nfx(root / "a.nfx", kind="ontology", name="A")
        idx = NfxIndex(root)
        assert idx.entries()[0].namespace is None
        assert idx.namespace_of(root) is None

    def test_token_collision_fatal(self, tmp_path):
        r1, r2 = tmp_path / "one" / ".nf", tmp_path / "two" / ".nf"
        _write_namespace(r1, "x")
        _write_namespace(r2, "x")
        with pytest.raises(exceptions.NfxViolation, match="token collision"):
            NfxIndex(r1, r2)

    def test_namespace_nid_collision_fatal(self, tmp_path):
        r1, r2 = tmp_path / "one" / ".nf", tmp_path / "two" / ".nf"
        nid = _write_namespace(r1, "x")
        _write_namespace(r2, "y", nid=nid)
        with pytest.raises(exceptions.NfxViolation, match="nid collision"):
            NfxIndex(r1, r2)
        r3 = tmp_path / "three" / ".nf"
        nid3 = _write_namespace(r3, "z")
        (r3 / "ontology").mkdir()
        (r3 / "ontology" / "A.nfx").write_text(json.dumps(
            {"type": "ontology", "nid": nid3, "version": "1.0", "name": "A"}))
        with pytest.raises(exceptions.NfxViolation, match="nid collision"):
            NfxIndex(r3)

    def test_declaration_elsewhere_fatal(self, tmp_path):
        legacy = tmp_path / "plugins"
        _write_namespace(legacy, "x")
        with pytest.raises(exceptions.NfxViolation, match="only <root>/namespace.nfx"):
            NfxIndex(legacy)
        root = tmp_path / ".nf"
        _write_namespace(root / "ontology", "y")
        with pytest.raises(exceptions.NfxViolation, match="namespace declaration"):
            NfxIndex(root)

    def test_malformed_declaration_fatal(self, tmp_path):
        root = tmp_path / ".nf"
        _write_namespace(root, "Bad Token")
        with pytest.raises(exceptions.NfxViolation, match="invalid namespace token"):
            NfxIndex(root)
        _write_namespace(root, "x", type_="ontology")
        with pytest.raises(exceptions.NfxViolation, match="reserved"):
            NfxIndex(root)


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

    def test_subdir_typeless_fatal(self, tmp_path):
        root = tmp_path / ".nf"
        (root / "knowledge").mkdir(parents=True)
        (root / "knowledge" / "K.nfx").write_text(json.dumps(
            {"nid": str(uuid.uuid4()), "version": "1.0", "name": "K"}))
        with pytest.raises(exceptions.NfxViolation, match="knowledge/ but declares type ''"):
            NfxIndex(root)

    def test_ontology_subdir_admits_metaontology(self, tmp_path):
        root = tmp_path / ".nf"
        _write_nfx(root / "ontology" / "metaontology.nfx", kind="metaontology", name="Metaontology")
        idx = OntologyIndex(root)
        assert idx.metaontology_path == root / "ontology" / "metaontology.nfx"
        _write_nfx(root / "knowledge" / "M.nfx", kind="metaontology", name="M")
        with pytest.raises(exceptions.NfxViolation, match="knowledge/"):
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
