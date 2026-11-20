"""
Unit tests for neuro.base.nf_repo - the hooks of a `.nf` root.
"""

import hashlib
import json
import os
import subprocess
import uuid

import pytest

from neuro.base import nf_repo, nfx

pytestmark = pytest.mark.unit

_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.org"}


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], env={**os.environ, **_ENV},
                          capture_output=True, text=True, check=True).stdout


class _Root:
    """A `.nf` root that is its own repo, with a P ← A ← B chain."""

    def __init__(self, path):
        self.path = path
        path.mkdir()
        _git(path, "init", "-q", "-b", "master")
        _git(path, "config", "core.hooksPath", "/dev/null")  # no global hooks in tests
        self.p, self.a, self.b = (str(uuid.uuid4()) for _ in range(3))
        self.pn, self.an, self.bn = (str(uuid.uuid4()) for _ in range(3))
        self.write("namespace.nfx", {"type": "namespace", "nid": str(uuid.uuid4()), "version": "1.0",
                                     "name": "Root", "namespace": ""})
        self.write("ontology/p.nfx", self.doc(self.p, "P", "1.0", nodes=[self.pn]))
        self.write("ontology/a.nfx", self.doc(self.a, "A", "1.0", deps=[(self.p, "1.0")], nodes=[self.an],
                                              rels=[(self.an, self.pn)]))
        self.write("knowledge/b.nfx", self.doc(self.b, "B", "1.0", kind="knowledge", deps=[(self.a, "1.0")],
                                               nodes=[self.bn], rels=[(self.bn, self.an)]))
        self.commit("ADD: root")
        for t in ("ontology/p/1.0", "ontology/a/1.0", "knowledge/b/1.0", "namespace/1.0"):
            _git(path, "tag", "-a", t, "-m", t)
        self.repo = nf_repo.Repo(path)

    @staticmethod
    def doc(nid, name, version, kind="ontology", deps=(), nodes=(), rels=(), extra=None, hash_=None):
        d = {"type": kind, "nid": nid, "version": version, "name": name}
        if extra:
            d["description"] = extra
        if deps:
            d["dependencies"] = [f"{n}@{v}" for n, v in deps]
        if hash_:
            d["hash"] = hash_
        if nodes:
            d["nodes"] = [{"nid": n, "labels": ["Thing"]} for n in nodes]
        if rels:
            d["relationships"] = [{"from": f, "to": t, "type": "LINKS"} for f, t in rels]
        return d

    def write(self, rel, data, add=True):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(nfx.dumps(nfx.Nfx.from_dict(data)) if isinstance(data, dict) else data)
        if add:
            _git(self.path, "add", rel)

    def commit(self, message):
        _git(self.path, "commit", "-q", "-m", message)

    def check(self):
        return self.repo.check().issues


@pytest.fixture
def root(tmp_path):
    return _Root(tmp_path / ".nf")


def test_check(root):
    assert root.check() == []
    # an unreleased edit: content changes, version stays at its tag
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn], extra="edited"))
    assert root.check() == []
    # a skipped version, then an already released one
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.2", nodes=[root.pn]))
    assert any("skips past the latest release 1.0" in i for i in root.check())
    _git(root.path, "tag", "-a", "ontology/p/1.1", "-m", "x", "HEAD")
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn], extra="edited"))
    assert any("version 1.0 is already released" in i for i in root.check())


def test_check_closure(root):
    # bumping P without re-pinning A is refused, naming A; with the closure it passes
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.1", nodes=[root.pn]))
    issues = root.check()
    assert len(issues) == 1 and "ontology/a.nfx: pins p@1.0" in issues[0]
    root.write("ontology/a.nfx", root.doc(root.a, "A", "1.1", deps=[(root.p, "1.1")], nodes=[root.an],
                                          rels=[(root.an, root.pn)]))
    root.write("knowledge/b.nfx", root.doc(root.b, "B", "1.1", kind="knowledge", deps=[(root.a, "1.1")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)]))
    verdict = root.repo.check()
    assert verdict.issues == []
    assert set(verdict.released) == {"ontology/p/1.1", "ontology/a/1.1", "knowledge/b/1.1"}


def test_check_dependants(root):
    # A drops the node B references: refused at A's commit, naming B
    root.write("ontology/a.nfx", root.doc(root.a, "A", "1.0", deps=[(root.p, "1.0")]))
    issues = root.check()
    assert any(i.startswith("knowledge/b.nfx: unresolved") for i in issues)


def test_check_rules(root):
    # an ontology may not pin knowledge
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", deps=[(root.b, "1.0")], nodes=[root.pn]))
    assert any("may not pin knowledge" in i for i in root.check())
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn]))
    # validators hash follows the validators file
    root.write("validators/p.py", "# v1\n")
    assert any("is not sha256(validators/p.py)" in i for i in root.check())
    digest = hashlib.sha256(b"# v1\n").hexdigest()
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn], hash_=digest))
    assert root.check() == []
    # the index is judged, not the worktree
    root.write("ontology/p.nfx", root.doc(root.p, "P", "9.9", nodes=[root.pn], hash_=digest), add=False)
    assert root.check() == []
    # labels split over lines
    text = json.dumps(root.doc(root.p, "P", "1.0", nodes=[root.pn], hash_=digest), indent=4)
    root.write("ontology/p.nfx", text)
    assert any("labels array must be on one line" in i for i in root.check())


def test_check_rev(root):
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.1", nodes=[root.pn]))
    root.commit("RELEASE: ontology P 1.1")
    assert any("pins p@1.0" in i for i in root.repo.check("HEAD").issues)
    assert root.repo.check("HEAD^").issues == []


def test_tag(root):
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn], extra="unreleased"))
    root.commit("UPDATE: p")
    assert root.repo.tag() == []
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.1", nodes=[root.pn]))
    root.write("ontology/a.nfx", root.doc(root.a, "A", "1.1", deps=[(root.p, "1.1")], nodes=[root.an],
                                          rels=[(root.an, root.pn)]))
    root.write("knowledge/b.nfx", root.doc(root.b, "B", "1.1", kind="knowledge", deps=[(root.a, "1.1")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)]))
    root.commit("RELEASE: ontology P 1.1")
    assert sorted(root.repo.tag()) == ["knowledge/b/1.1", "ontology/a/1.1", "ontology/p/1.1"]
    assert root.repo.tag() == []
    assert _git(root.path, "cat-file", "-t", "ontology/p/1.1").strip() == "tag"
    assert "RELEASE: ontology P 1.1" in _git(root.path, "cat-file", "-p", "ontology/a/1.1")


def test_release(root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    with pytest.raises(ValueError, match="nothing to release"):
        root.repo.release(["p"])
    # P edited (unreleased), B edited too; releasing P carries the closure in one commit
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn], extra="edited"), add=False)
    root.write("knowledge/b.nfx", root.doc(root.b, "B", "1.0", kind="knowledge", deps=[(root.a, "1.0")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)], extra="b edit"), add=False)
    steps = root.repo.plan_release(["P"])
    assert [(s.rel.stem, s.old, s.new, s.repins, s.carries) for s in steps] == [
        ("p", "1.0", "1.1", [], False), ("a", "1.0", "1.1", ["p@1.1"], False), ("b", "1.0", "1.1", ["a@1.1"], True)]
    sha, steps, tags = root.repo.release(["p"])
    assert tags == ["knowledge/b/1.1", "ontology/a/1.1", "ontology/p/1.1"]
    assert _git(root.path, "show", "--name-only", "--format=%s", sha).split("\n")[0] == "RELEASE: ontology P 1.1"
    body = _git(root.path, "log", "-1", "--format=%b").strip().splitlines()
    assert body == ["A 1.0 → 1.1 (re-pin p@1.1)", "B 1.0 → 1.1 (re-pin a@1.1; carries unreleased edits)"]
    assert "re-pin p@1.1" in _git(root.path, "cat-file", "-p", "ontology/a/1.1")
    assert root.repo.check("HEAD").issues == []
    assert _git(root.path, "status", "--short") == ""


def test_release_refused(root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    # P drops the node A references: refused, worktree and index put back
    edited = root.doc(root.p, "P", "1.0", nodes=[str(uuid.uuid4())])
    root.write("ontology/p.nfx", edited, add=False)
    before = (root.path / "ontology/p.nfx").read_text()
    with pytest.raises(nf_repo.ReleaseRefused) as e:
        root.repo.release(["p"])
    assert any(i.startswith("ontology/a.nfx: unresolved") for i in e.value.issues)
    assert (root.path / "ontology/p.nfx").read_text() == before
    assert _git(root.path, "diff", "--cached", "--name-only") == ""
    # a foreign staged file blocks the release
    root.write("ruff.toml", "[lint]\n")
    with pytest.raises(ValueError, match="already holds ruff.toml"):
        root.repo.release(["p"])


def test_install(root):
    hooks = root.path / ".git" / "hooks"
    wrote = root.repo.install(runner="wrapper")
    assert {p.split("/")[-1] for p in wrote} == {"pre-commit", "post-commit"}
    assert (root.path / ".githooks" / "pre-commit").read_text().count("nf.check --root") == 1
    assert ".githooks/post-commit" in (hooks / "post-commit").read_text()
    assert _git(root.path, "config", "nf.runner").strip() == "wrapper"
    assert root.repo.install(runner="wrapper") == []
    (hooks / "pre-commit").write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(FileExistsError):
        root.repo.install(runner="wrapper")
    assert "echo invoke" not in (root.path / ".githooks" / "pre-commit").read_text()


def test_series():
    from pathlib import Path
    assert nf_repo.series_of(Path("ontology/Cli.nfx")) == ("ontology", "cli")
    assert nf_repo.series_of(Path("namespace.nfx")) == ("namespace", "")
    assert nf_repo.series_of(Path("tests/x.nfx")) is None
    assert nf_repo.tag_name(("namespace", ""), "1.2") == "namespace/1.2"
    assert nf_repo.parse_tag("knowledge/facts/1.1") == (("knowledge", "facts"), "1.1")
