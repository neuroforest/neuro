"""
Unit tests for neuro.base.nf_history - legacy plugins history → `.nf` repo.
"""

import json
import os
import subprocess
import uuid

import pytest

from neuro.base import nf_history, nf_import

pytestmark = pytest.mark.unit

_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.org"}


def _git(repo, *args, when=None):
    env = {**os.environ, **_ENV}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{when} +0000"
    return subprocess.run(["git", "-C", str(repo), *args], env=env,
                          capture_output=True, text=True, check=True).stdout


def _doc(nid, name, version, kind="ontology", deps=(), extra=None):
    doc = {"type": kind, "nid": nid, "version": version, "name": name}
    if kind is None:
        del doc["type"]
    if deps:
        doc["dependencies"] = list(deps)
    if extra:
        doc["description"] = extra
    return doc


class _Legacy:
    """A legacy plugins repo built commit by commit."""

    def __init__(self, path):
        self.path = path
        self.t = 1_700_000_000
        path.mkdir()
        _git(path, "init", "-q", "-b", "master")

    def commit(self, message, files, tag=None, gap=60, remove=()):
        self.t += gap
        for rel, doc in files.items():
            p = self.path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(doc) if isinstance(doc, dict) else doc)
            _git(self.path, "add", rel)
        for rel in remove:
            _git(self.path, "rm", "-q", rel)
        _git(self.path, "commit", "-q", "-m", message, when=self.t)
        if tag:
            _git(self.path, "tag", tag)


def _ns():
    return nf_import.namespace_doc(str(uuid.uuid4()), str(uuid.uuid4()), "1.0")


def _ids():
    return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def test_is_repin():
    a = _doc("n", "A", "1.0", deps=["d@1.0"])
    assert nf_history.is_repin(a, _doc("n", "A", "1.1", deps=["d@1.1"]))
    assert not nf_history.is_repin(a, _doc("n", "A", "1.1", deps=["d@1.1"], extra="edited"))
    assert not nf_history.is_repin(a, _doc("n", "A", "1.1", deps=["d@1.0", "e@1.0"]))
    assert not nf_history.is_repin(a, a)


def test_group(tmp_path):
    p, a, b = _ids()
    repo = _Legacy(tmp_path / "plugins")
    repo.commit("ADD: p", {"p.nfx": _doc(p, "P", "1.0")}, tag="p/1.0")
    repo.commit("ADD: a, b", {"a.nfx": _doc(a, "A", "1.0", deps=[f"{p}@1.0"]),
                              "b.nfx": _doc(b, "B", "1.0", deps=[f"{p}@1.0"])}, gap=3600)
    # release P, its re-pin cascade, and a bottom-up second release pinning it
    repo.commit("RELEASE: P 1.1", {"p.nfx": _doc(p, "P", "1.1", extra="x")}, tag="p/1.1", gap=3600)
    repo.commit("UPDATE: dependency", {"a.nfx": _doc(a, "A", "1.1", deps=[f"{p}@1.1"])}, tag="a/1.1")
    repo.commit("RELEASE: B 1.1", {"b.nfx": _doc(b, "B", "1.1", deps=[f"{p}@1.1"], extra="y")}, tag="b/1.1")
    # a second write of A inside the window starts a new event
    repo.commit("UPDATE: dependency", {"a.nfx": _doc(a, "A", "1.2", deps=[f"{p}@1.1"], extra="z")})
    events = nf_history.group(nf_history.read_log(repo.path))
    subjects = [[c.subject for c in e.members] for e in events]
    assert subjects == [
        ["ADD: p"], ["ADD: a, b"],
        ["RELEASE: P 1.1", "UPDATE: dependency", "RELEASE: B 1.1"],
        ["UPDATE: dependency"],
    ]


def test_rename_in():
    table = {"Antimicrobial agents": "antimicrobial-agents", "Custom antimicrobial agents": "custom-antimicrobial-agents",
             "LAB": "lab", "Blob": "blob"}
    assert nf_history.rename_in("RELEASE: knowledge Custom antimicrobial agents 1.7", table) \
        == "RELEASE: knowledge custom-antimicrobial-agents 1.7"
    assert nf_history.rename_in("UPDATE: dependency - re-pin Blob@2.1 for LAB", table) \
        == "UPDATE: dependency - re-pin blob@2.1 for lab"
    assert nf_history.rename_in("ADD: LAB-DS, Blobs", table) == "ADD: LAB-DS, Blobs"   # inside a longer name
    table[""] = {"demo", "kappa"}
    # a stem in another case only in the subject's module slot; the project name Kappa stays
    assert nf_history.rename_in("RELEASE: ontology Demo 3.0 for Kappa", table) == "RELEASE: ontology demo 3.0 for Kappa"


def test_drop_duplicates(tmp_path):
    nid = str(uuid.uuid4())
    (tmp_path / "tw5").mkdir()
    (tmp_path / "tw5.nfx").write_text(json.dumps(_doc(nid, "TW5", "1.4")))
    (tmp_path / "tw5" / "tw5.nfx").write_text(json.dumps(_doc(nid, "TW5", "1.5")))
    dropped = nf_history.drop_duplicates(tmp_path)
    assert len(dropped) == 1 and dropped[0].startswith("tw5.nfx")
    assert not (tmp_path / "tw5.nfx").exists()


def test_build(tmp_path):
    p, a, k = _ids()
    repo = _Legacy(tmp_path / "plugins")
    repo.commit("ADD: p", {"p.nfx": _doc(p, "P", "1.0", kind=None)}, tag="p/1.0")
    repo.commit("ADD: k", {"facts.nfx": _doc(k, "Facts", "1.0", kind="knowledge", deps=[f"{p}@1.0"])},
                gap=3600)
    repo.commit("RELEASE: P 1.1", {"p.nfx": _doc(p, "P", "1.1", extra="typed now")}, tag="p/1.1", gap=3600)
    repo.commit("UPDATE: dependency",
                {"facts.nfx": _doc(k, "Facts", "1.1", kind="knowledge", deps=[f"{p}@1.1"])})
    repo.commit("ADD: a", {"alpha/alpha.nfx": _doc(a, "Alpha", "1.0", deps=[f"{p}@1.1"])},
                tag="alpha/1.0", gap=3600)
    repo.commit("ADD: notes on Alpha", {".scripts/notes.txt": "only unmapped files"}, gap=3600)

    dst = tmp_path / "out" / ".nf"
    report = nf_history.build(repo.path, dst, _ns(), tmp_path / "scratch")
    assert (report.commits, report.events, report.legacy_tags, report.empty) == (6, 4, 3, 1)
    assert (report.tags, report.synthesized) == (6, 3)
    assert report.fatal == [] and report.unmapped_tags == []
    log = _git(dst, "log", "--format=%s").splitlines()
    assert log == ["ADD: a", "RELEASE: p 1.1", "ADD: k", "ADD: p"]   # names → stems, the empty commit dropped
    assert set(_git(dst, "tag").split()) == {
        "ontology/p/1.0", "ontology/p/1.1", "ontology/alpha/1.0",
        "knowledge/facts/1.0", "knowledge/facts/1.1",   # untagged in the legacy repo
        "namespace/1.0",                                # the declaration, on the first commit
    }
    assert "synthesized" in _git(dst, "cat-file", "-p", "knowledge/facts/1.1")
    assert "RELEASE: p 1.1" in _git(dst, "cat-file", "-p", "ontology/p/1.1")
    assert _git(dst, "rev-list", "-n1", "namespace/1.0") == _git(dst, "rev-list", "--max-parents=0", "HEAD")
    # every name, in every commit, is its stem
    for sha in _git(dst, "rev-list", "HEAD").split():
        for rel in _git(dst, "ls-tree", "-r", "--name-only", sha).split():
            if rel.endswith(".nfx") and rel != "namespace.nfx":
                assert json.loads(_git(dst, "show", f"{sha}:{rel}"))["name"] == rel.rsplit("/", 1)[1][:-4]
    # the typeless first P is placed by the type it later declared
    assert "ontology/p.nfx" in _git(dst, "ls-tree", "-r", "--name-only", "ontology/p/1.0")
    assert _git(dst, "cat-file", "-t", "ontology/p/1.1").strip() == "tag"
    assert nf_history.check_tags(dst) == []
    head = set(_git(dst, "ls-tree", "-r", "--name-only", "HEAD").split())
    assert head == {"namespace.nfx", "ontology/p.nfx", "ontology/alpha.nfx", "knowledge/facts.nfx"}


def test_release_changes():
    from pathlib import Path

    a, k, j = _ids()

    def tree(av, kv, k_extra=None, validators=b"v1"):
        """A ← K ← J: K pins A, J pins K; the legacy pins follow the legacy versions."""
        def move(rel, doc, nid):
            return nf_import.Move(None, Path(rel), json.dumps(doc, indent=4).encode(), nid=nid, name=doc["name"])
        return [move("ontology/a.nfx", _doc(a, "a", av), a),
                move("knowledge/k.nfx", _doc(k, "k", kv, "knowledge", [f"{a}@{av}"], k_extra), k),
                move("knowledge/j.nfx", _doc(j, "j", "1.0", "knowledge", [f"{k}@{kv}"]), j),
                nf_import.Move(None, Path("validators/a.py"), validators)]

    state = nf_history.Releases()

    def step(*args, **kwargs):
        out = nf_history.release_changes(tree(*args, **kwargs), state)
        docs = {rel.stem: json.loads(content) for rel, content in out.items()}
        return {stem: d["version"] for stem, d in docs.items()}, docs

    # first appearance: as the legacy repo has it
    assert step("1.0", "1.0")[0] == {"a": "1.0", "k": "1.0", "j": "1.0"} and state.bumped == 0
    # A released; the legacy hook re-pinned K without a bump, and never touched J
    versions, docs = step("1.1", "1.0")
    assert versions == {"a": "1.1", "k": "1.1", "j": "1.1"} and state.bumped == 2
    assert docs["k"]["dependencies"] == [f"{a}@1.1"] and docs["j"]["dependencies"] == [f"{k}@1.1"]
    # nothing changed: nothing is released
    assert step("1.1", "1.0")[0] == versions and state.bumped == 2
    # K rewritten at its legacy version: K and its dependant move on
    assert step("1.1", "1.0", k_extra="x")[0] == {"a": "1.1", "k": "1.2", "j": "1.2"}
    # the legacy repo releases K as 1.1, behind what was written: the next minor after that
    versions, docs = step("1.1", "1.1", k_extra="y")
    assert versions == {"a": "1.1", "k": "1.3", "j": "1.3"} and docs["j"]["dependencies"] == [f"{k}@1.3"]
    # a legacy release that is ahead is taken as it is
    assert step("1.1", "2.0", k_extra="y")[0] == {"a": "1.1", "k": "2.0", "j": "1.4"}
    # the validators are part of the module: their change releases it, and the cascade follows
    assert step("1.1", "2.0", k_extra="y", validators=b"v2")[0] == {"a": "1.2", "k": "2.1", "j": "1.5"}
