"""
Unit tests for neuro.base.nf_split - partitioning a `.nf` root's repository.
"""

import pytest

from neuro.base import nf_repo, nf_split
from tests.base.test_nf_repo import _git, _Root

pytestmark = pytest.mark.unit


@pytest.fixture
def root(tmp_path):
    return _Root(tmp_path / ".nf")  # the P ← A ← B chain


def _released(root):
    """The fixture after one cascade release of P: two commits, both touching every module."""
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], extra="edited"), add=False)
    root.write("ruff.toml", "[lint]\n")
    root.commit("ADD: ruff")
    root.repo.release(["p"])
    return root.path.parent / "kb" / ".nf"


def _subjects(repo):
    return _git(repo, "log", "--format=%s").splitlines()


def test_plan(root):
    to = _released(root)
    to.parent.mkdir()
    p = nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["b"]}])
    assert [(o.word, o.commits, o.tags, sorted(o.needs)) for o in p.outputs] == [("root", 3, 5, []), ("kb", 2, 2, [""])]
    assert (p.commits, p.shared) == (3, 2) and p.outputs[1].needs[""] == ["b → a"]
    assert p.continuation.namespace.version == "1.0"
    assert [d[0] for d in p.outputs[1].namespace.dependencies] == [p.continuation.namespace.nid]
    # A alone: B, staying, needs it, and it needs P - the two parts would pin each other
    with pytest.raises(nf_split.SplitRefused) as e:
        nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["a"]}])
    assert any("depend on each other: root → kb → root" in i for i in e.value.issues)
    p = nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["a"]}], with_dependants=True)
    assert sorted(p.stems[n][1] for n in p.outputs[1].modules) == ["a", "b"]
    # P leaves, its dependants stay: the continuation pins the new root, and its declaration is released
    p = nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["p"]}])
    assert sorted(p.continuation.needs) == ["kb"] and p.continuation.namespace.version == "1.1"
    with pytest.raises(nf_split.SplitRefused) as e:
        nf_split.plan(root.repo, [{"token": "root", "to": to, "modules": ["zz"]},
                                  {"token": "kb", "to": root.path, "modules": []}])
    assert len(e.value.issues) == 3
    # a published root is split only on purpose
    _git(root.path, "remote", "add", "mirror", "ssh://example.org/x.git")
    with pytest.raises(nf_split.SplitRefused) as e:
        nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["b"]}])
    assert "--rewrite-published" in e.value.issues[0]
    assert nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["b"]}], rewrite_published=True)


def test_build(root):
    to = _released(root)
    to.parent.mkdir()
    source_shas = _git(root.path, "rev-list", "--reverse", "HEAD").split()
    p = nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["b"]}])
    state = nf_split.build(p)
    cont, kb = (o["dir"] for o in state["outputs"])
    assert _subjects(kb) == ["MIGRATE: split ← root", "RELEASE: ontology p 1.1", "ADD: root"]
    assert _subjects(cont) == ["MIGRATE: split → kb", "RELEASE: ontology p 1.1", "ADD: ruff", "ADD: root"]
    assert _git(cont, "log", "-1", "--format=%b").strip() == "knowledge b"
    # one release, one commit in each part; each body speaks only of its own documents
    assert _git(kb, "log", "-1", "--format=%b", "HEAD~1").strip() == "b 1.0 → 1.1 (re-pin a@1.1)"
    assert _git(cont, "log", "-1", "--format=%b", "HEAD~1").strip() == "a 1.0 → 1.1 (re-pin p@1.1)"
    assert sorted(_git(kb, "ls-files").split()) == ["knowledge/b.nfx", "namespace.nfx", "ruff.toml"]
    assert sorted(_git(cont, "ls-files").split()) == ["namespace.nfx", "ontology/a.nfx", "ontology/p.nfx", "ruff.toml"]
    assert _git(kb, "tag").split() == ["knowledge/b/1.0", "knowledge/b/1.1", "namespace/1.0"]
    assert _git(cont, "tag").split() == ["namespace/1.0", "ontology/a/1.0", "ontology/a/1.1",
                                         "ontology/p/1.0", "ontology/p/1.1"]
    assert _git(kb, "rev-parse", "knowledge/b/1.1^{commit}") == _git(kb, "rev-parse", "HEAD~1")
    assert "re-pin a@1.1" in _git(kb, "cat-file", "-p", "knowledge/b/1.1")
    # dates and authors travel; the note names the commit each one was made from
    assert _git(kb, "log", "--format=%an %ad %cd", "HEAD~1") == _git(root.path, "log", "--format=%an %ad %cd",
                                                                    source_shas[2], "--", "knowledge/b.nfx")
    note = _git(kb, "notes", "--ref", "nf-origin", "show", "HEAD~2").split()
    assert note == [source_shas[0], state["namespace"]]
    assert nf_split.verify(p.staging) == []
    assert not (p.staging / "kb" / ".nf" / ".git" / "objects" / "info" / "alternates").exists()
    with pytest.raises(FileExistsError):
        nf_split.build(p)


def test_swap(root):
    to = _released(root)
    to.parent.mkdir()
    p = nf_split.plan(root.repo, [{"token": "kb", "to": to, "modules": ["b"]}])
    nf_split.build(p)
    root.write("ruff.toml", "[lint]\n# edit\n", add=False)
    with pytest.raises(nf_split.SplitRefused, match="1 issue"):
        nf_split.swap(p.staging)
    _git(root.path, "checkout", "-q", "--", "ruff.toml")
    state = nf_split.swap(p.staging, notify=False)
    assert state["kept"] == str(root.path.parent / ".nf.pre-split") and not p.staging.exists()
    assert _subjects(root.path)[0] == "MIGRATE: split → kb" and _subjects(to)[0] == "MIGRATE: split ← root"
    assert _git(root.path, "status", "--short") == "" and _git(to, "status", "--short") == ""
    # the two roots stand together: the new one's module still resolves its pin into the old
    assert nf_repo.Repo(to).check("HEAD", others=[root.path]).issues == []
    # the log names the root each commit was made in: the source's, before the split
    entries, note = nf_repo.module_log(nf_repo.Repo(to), "b", roots=[root.path])
    assert note is None and [(e.token, e.subject, e.version) for e in entries] == [
        ("kb", "MIGRATE: split ← root", ""), ("", "RELEASE: ontology p 1.1", "1.1"), ("", "ADD: root", "1.0")]


def test_rename(root):
    import json

    to = _released(root)
    to.parent.mkdir()
    part = {"token": "kb", "to": to, "modules": ["b"], "nid": "0d1f0f0a-6c0e-4b7e-9d0a-3a3b1f1f7a11"}
    with pytest.raises(nf_split.SplitRefused) as e:
        nf_split.plan(root.repo, [{**part, "rename": {"b": "Not A Stem", "a": "x"}, "nid": "nope"}])
    assert len(e.value.issues) == 3
    # the new root's history is written as if the module had always had the stem
    p = nf_split.plan(root.repo, [{**part, "strip_prefix": "x-", "rename": {"b": "bee"}}])
    assert p.restem == {"b": "bee"} and p.outputs[1].namespace.nid == part["nid"]
    state = nf_split.build(p)
    cont, kb = (o["dir"] for o in state["outputs"])
    assert state["unedited"] == [] and state["outputs"][1]["renamed"] == {"b": "bee"}
    assert sorted(_git(kb, "ls-files").split()) == ["knowledge/bee.nfx", "namespace.nfx", "ruff.toml"]
    assert _git(kb, "tag").split() == ["knowledge/bee/1.0", "knowledge/bee/1.1", "namespace/1.0"]
    assert [json.loads(_git(kb, "show", f"{rev}:knowledge/bee.nfx"))["name"] for rev in ("HEAD", "HEAD~2")] == ["bee"] * 2
    assert _git(kb, "log", "-1", "--format=%b", "HEAD~1").strip() == "bee 1.0 → 1.1 (re-pin a@1.1)"
    assert _git(kb, "cat-file", "-p", "knowledge/bee/1.1").splitlines()[-1].startswith("knowledge/bee/1.1")
    assert _git(cont, "log", "-1", "--format=%b").strip() == "knowledge bee"
    assert nf_split.verify(p.staging) == []
    assert nf_split._restem("RELEASE: ontology b-x 1.1 - re-pin b 1.1\nabout b\n", {"b": "bee"}) == \
        "RELEASE: ontology b-x 1.1 - re-pin bee 1.1\nabout b\n"


def test_message():
    message = "RELEASE: ontology p 1.1\n\na 1.0 → 1.1 (re-pin p@1.1)\nb 1.0 → 1.1 (re-pin a@1.1)\nfree text\n"
    assert nf_split._message(message, {"b"}, {"p", "a"}) == \
        "RELEASE: ontology p 1.1\n\nb 1.0 → 1.1 (re-pin a@1.1)\nfree text\n"
    assert nf_split._message("ADD: x\n", {"b"}, {"p"}) == "ADD: x\n"
    moved = "MIGRATE: ontology p → kb\n\nMIGRATE: ontology p → kb\nMIGRATE: knowledge b → kb · released\n"
    assert nf_split._message(moved, {"p"}, {"b"}) == "MIGRATE: ontology p → kb\n\nMIGRATE: ontology p → kb\n"
