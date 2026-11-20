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
        self.write("ontology/p.nfx", self.doc(self.p, "p", "1.0", nodes=[self.pn]))
        self.write("ontology/a.nfx", self.doc(self.a, "a", "1.0", deps=[(self.p, "1.0")], nodes=[self.an],
                                              rels=[(self.an, self.pn)]))
        self.write("knowledge/b.nfx", self.doc(self.b, "b", "1.0", kind="knowledge", deps=[(self.a, "1.0")],
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
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], extra="edited"))
    assert root.check() == []
    # a skipped version, then an already released one
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.2", nodes=[root.pn]))
    assert any("skips past the latest release 1.0" in i for i in root.check())
    _git(root.path, "tag", "-a", "ontology/p/1.1", "-m", "x", "HEAD")
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], extra="edited"))
    assert any("version 1.0 is already released" in i for i in root.check())


def test_check_closure(root):
    # bumping P without re-pinning A is refused, naming A; with the closure it passes
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.1", nodes=[root.pn]))
    issues = root.check()
    assert len(issues) == 1 and "ontology/a.nfx: pins p@1.0" in issues[0]
    root.write("ontology/a.nfx", root.doc(root.a, "a", "1.1", deps=[(root.p, "1.1")], nodes=[root.an],
                                          rels=[(root.an, root.pn)]))
    root.write("knowledge/b.nfx", root.doc(root.b, "b", "1.1", kind="knowledge", deps=[(root.a, "1.1")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)]))
    verdict = root.repo.check()
    assert verdict.issues == []
    assert set(verdict.released) == {"ontology/p/1.1", "ontology/a/1.1", "knowledge/b/1.1"}


def test_check_name(root):
    # name = stem on every touched document
    root.write("ontology/p.nfx", root.doc(root.p, "P", "1.0", nodes=[root.pn], extra="edited"))
    assert any("name 'P' must be its stem 'p'" in i for i in root.check())


def test_check_dependants(root):
    # A drops the node B references: refused at A's commit, naming B
    root.write("ontology/a.nfx", root.doc(root.a, "a", "1.0", deps=[(root.p, "1.0")]))
    issues = root.check()
    assert any(i.startswith("knowledge/b.nfx: unresolved") for i in issues)


def test_check_rules(root):
    # an ontology may not pin knowledge
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", deps=[(root.b, "1.0")], nodes=[root.pn]))
    assert any("may not pin knowledge" in i for i in root.check())
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn]))
    # validators hash follows the validators file
    root.write("validators/p.py", "# v1\n")
    assert any("is not sha256(validators/p.py)" in i for i in root.check())
    digest = hashlib.sha256(b"# v1\n").hexdigest()
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], hash_=digest))
    assert root.check() == []
    # the index is judged, not the worktree
    root.write("ontology/p.nfx", root.doc(root.p, "p", "9.9", nodes=[root.pn], hash_=digest), add=False)
    assert root.check() == []
    # labels split over lines
    text = json.dumps(root.doc(root.p, "p", "1.0", nodes=[root.pn], hash_=digest), indent=4)
    root.write("ontology/p.nfx", text)
    assert any("labels array must be on one line" in i for i in root.check())


def test_check_rev(root):
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.1", nodes=[root.pn]))
    root.commit("RELEASE: ontology p 1.1")
    assert any("pins p@1.0" in i for i in root.repo.check("HEAD").issues)
    assert root.repo.check("HEAD^").issues == []


def test_tag(root):
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], extra="unreleased"))
    root.commit("UPDATE: p")
    assert root.repo.tag() == []
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.1", nodes=[root.pn]))
    root.write("ontology/a.nfx", root.doc(root.a, "a", "1.1", deps=[(root.p, "1.1")], nodes=[root.an],
                                          rels=[(root.an, root.pn)]))
    root.write("knowledge/b.nfx", root.doc(root.b, "b", "1.1", kind="knowledge", deps=[(root.a, "1.1")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)]))
    root.commit("RELEASE: ontology p 1.1")
    assert sorted(root.repo.tag()) == ["knowledge/b/1.1", "ontology/a/1.1", "ontology/p/1.1"]
    assert root.repo.tag() == []
    assert _git(root.path, "cat-file", "-t", "ontology/p/1.1").strip() == "tag"
    assert "RELEASE: ontology p 1.1" in _git(root.path, "cat-file", "-p", "ontology/a/1.1")


def test_release(root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    with pytest.raises(ValueError, match="nothing to release"):
        root.repo.release(["p"])
    # P edited (unreleased), B edited too; releasing P carries the closure in one commit
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], extra="edited"), add=False)
    root.write("knowledge/b.nfx", root.doc(root.b, "b", "1.0", kind="knowledge", deps=[(root.a, "1.0")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)], extra="b edit"), add=False)
    steps = root.repo.plan_release(["P"])
    assert [(s.rel.stem, s.old, s.new, s.repins, s.carries) for s in steps] == [
        ("p", "1.0", "1.1", [], False), ("a", "1.0", "1.1", ["p@1.1"], False), ("b", "1.0", "1.1", ["a@1.1"], True)]
    sha, steps, tags = root.repo.release(["p"])
    assert tags == ["knowledge/b/1.1", "ontology/a/1.1", "ontology/p/1.1"]
    assert _git(root.path, "show", "--name-only", "--format=%s", sha).split("\n")[0] == "RELEASE: ontology p 1.1"
    body = _git(root.path, "log", "-1", "--format=%b").strip().splitlines()
    assert body == ["a 1.0 → 1.1 (re-pin p@1.1)", "b 1.0 → 1.1 (re-pin a@1.1; carries unreleased edits)"]
    assert "re-pin p@1.1" in _git(root.path, "cat-file", "-p", "ontology/a/1.1")
    assert root.repo.check("HEAD").issues == []
    assert _git(root.path, "status", "--short") == ""


def test_release_refused(root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    # P drops the node A references: refused, worktree and index put back
    edited = root.doc(root.p, "p", "1.0", nodes=[str(uuid.uuid4())])
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


def test_rename(root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    validators = "class Even:\n    pass\n"
    digest = hashlib.sha256(validators.encode()).hexdigest()
    root.write("validators/p.py", validators)
    root.write("tests/test_p.py", '_P_VALIDATORS = Path(__file__).parents[1] / "validators" / "p.py"\n')
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.1", nodes=[root.pn], hash_=digest))
    root.write("ontology/a.nfx", root.doc(root.a, "a", "1.1", deps=[(root.p, "1.1")], nodes=[root.an],
                                          rels=[(root.an, root.pn)]))
    root.write("knowledge/b.nfx", root.doc(root.b, "b", "1.1", kind="knowledge", deps=[(root.a, "1.1")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)]))
    root.commit("RELEASE: ontology p 1.1")
    for t in ("ontology/p/1.1", "ontology/a/1.1", "knowledge/b/1.1"):
        _git(root.path, "tag", "-a", t, "-m", f"{t} — RELEASE: ontology p 1.1")
    released = _git(root.path, "rev-parse", "ontology/p/1.1^{commit}").strip()

    for bad, match in (("P2", "not a stem"), ("p", "already"), ("a", "taken"), ("zz", "no such module")):
        with pytest.raises(ValueError, match=match):
            root.repo.rename("zz" if bad == "zz" else "p", "q" if bad == "zz" else bad)

    sha, plan = root.repo.rename("p", "probe")
    assert _git(root.path, "log", "-1", "--format=%s", sha).strip() == "REFACTOR: ontology p → probe"
    assert {str(b) for _, b in plan.files} == {"ontology/probe.nfx", "validators/probe.py", "tests/test_probe.py"}
    assert json.loads((root.path / "ontology/probe.nfx").read_text())["name"] == "probe"
    assert '"validators" / "probe.py"' in (root.path / "tests/test_probe.py").read_text()
    assert sorted(_git(root.path, "tag", "-l", "ontology/p*").split()) == ["ontology/probe/1.0", "ontology/probe/1.1"]
    assert _git(root.path, "rev-parse", "ontology/probe/1.1^{commit}").strip() == released
    assert "renamed from ontology/p/1.1" in _git(root.path, "cat-file", "-p", "ontology/probe/1.1")
    assert root.repo.check("HEAD").issues == []
    assert _git(root.path, "status", "--short") == ""
    follow = _git(root.path, "log", "--follow", "--format=%s", "--", "ontology/probe.nfx").splitlines()
    assert follow[0] == "REFACTOR: ontology p → probe" and follow[-1] == "ADD: root"
    # the next release continues the series under the new stem
    root.write("ontology/probe.nfx", root.doc(root.p, "probe", "1.1", nodes=[root.pn], hash_=digest, extra="x"),
               add=False)
    assert root.repo.plan_release(["probe"])[0].new == "1.2"
    _git(root.path, "checkout", "--", "ontology/probe.nfx")
    root.write("ruff.toml", "[lint]\n")
    with pytest.raises(ValueError, match="index is not empty"):
        root.repo.rename("probe", "p")


def test_rename_refused(root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    # a hash with no validators file: the rename's verdict refuses, and nothing moved
    root.write("ontology/p.nfx", root.doc(root.p, "p", "1.0", nodes=[root.pn], hash_="ab" * 32))
    root.commit("EDIT: p")
    with pytest.raises(nf_repo.ReleaseRefused):
        root.repo.rename("p", "probe")
    assert (root.path / "ontology/p.nfx").is_file() and not (root.path / "ontology/probe.nfx").exists()
    assert _git(root.path, "tag", "-l", "ontology/probe/*") == ""
    assert _git(root.path, "status", "--short") == ""


def _target(tmp_path, root, pin=True):
    """A second root, token `micro`, its envelope pinning the first one's namespace."""
    path = tmp_path / "micro" / ".nf"
    path.parent.mkdir()
    path.mkdir()
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "core.hooksPath", "/dev/null")
    _git(path, "config", "user.name", "T")
    _git(path, "config", "user.email", "t@example.org")
    ns = json.loads((root.path / "namespace.nfx").read_text())
    doc = {"type": "namespace", "nid": str(uuid.uuid4()), "version": "1.0", "name": "Micro", "namespace": "micro"}
    if pin:
        doc["dependencies"] = [f"{ns['nid']}@{ns['version']}"]
    (path / "namespace.nfx").write_text(nfx.dumps(nfx.Nfx.from_dict(doc)))
    _git(path, "add", "namespace.nfx")
    _git(path, "commit", "-q", "-m", "ADD: namespace")
    return nf_repo.Repo(path)


def test_move(tmp_path, root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    micro = _target(tmp_path, root)
    roots = [root.path, micro.root]
    # A has a dependant (B) in the source: refused alone, named
    with pytest.raises(ValueError, match="in-root dependants: knowledge/b.nfx"):
        nf_repo.plan_move(root.repo, micro, "a", others=roots)

    plan, departed, arrived = nf_repo.move(root.repo, micro, "b", as_="stains", others=roots)
    assert _git(root.path, "log", "-1", "--format=%s").strip() == "MIGRATE: knowledge b → micro"
    assert _git(micro.root, "log", "-1", "--format=%s%n%b").split("\n")[:2] == [
        "MIGRATE: knowledge b ← root as stains",
        f"MIGRATE: knowledge b ← root as stains · released in root as knowledge/b/1.0 at "
        f"{plan.items[0].released_at[:12]}"]
    assert not (root.path / "knowledge/b.nfx").exists()
    assert json.loads((micro.root / "knowledge/stains.nfx").read_text())["name"] == "stains"
    assert _git(root.path, "tag", "-l", "knowledge/*").split() == ["knowledge/b/1.0"]  # the source keeps its past
    assert "MIGRATE: knowledge b ← root as stains · released in root" in _git(
        micro.root, "cat-file", "-p", "knowledge/stains/1.0")
    assert root.repo.check("HEAD").issues == [] and micro.check("HEAD", others=roots).issues == []
    from neuro.base import nf_events
    arrival = nf_events.parse(_git(micro.root, "log", "-1", "--format=%s"))
    assert nf_events.departure_of(root.path, "", arrival, root.b, "micro") == departed

    # P with its dependant A as a set, while micro's stains already pins A: one commit at each end
    plan, departed, arrived = nf_repo.move(root.repo, micro, "p", with_dependants=True, others=roots)
    assert [i.stem for i in plan.items] == ["p", "a"]
    assert _git(root.path, "log", "-1", "--format=%B").strip().split("\n") == [
        "MIGRATE: ontology p → micro", "", "MIGRATE: ontology p → micro", "MIGRATE: ontology a → micro"]
    message = _git(micro.root, "log", "-1", "--format=%B")
    assert [e.subject for e in nf_events.parse_all(message)] == [
        "MIGRATE: ontology p ← root", "MIGRATE: ontology a ← root"]
    assert "MIGRATE: ontology a ← root · released in root as ontology/a/1.0" in _git(
        micro.root, "cat-file", "-p", "ontology/a/1.0")
    a_arrival = nf_events.parse_all(message)[1]
    assert nf_events.departure_of(root.path, "", a_arrival, root.a, "micro") == departed
    assert micro.check("HEAD", others=roots).issues == []

    # stains alone cannot go back: it pins A, now in micro, which the root's envelope does not reach
    with pytest.raises(nf_repo.ReleaseRefused) as e:
        nf_repo.plan_move(micro, root.repo, "stains", as_="b", others=roots)
    assert any("add micro@1.0" in i for i in e.value.issues)
    # the whole set goes back; the root's own tags of the same nids do not reserve p and a against them
    plan, _, _ = nf_repo.move(micro, root.repo, "p", with_dependants=True, others=roots)
    assert [(i.stem, i.landed) for i in plan.items] == [("p", "p"), ("a", "a"), ("stains", "stains")]
    assert _git(root.path, "log", "-1", "--format=%s").strip() == "MIGRATE: ontology p ← micro"
    assert root.repo.check("HEAD").issues == [] and micro.check("HEAD", others=roots).issues == []
    assert sorted(_git(root.path, "tag", "-l", "ontology/*").split()) == [
        "ontology/a/1.0", "ontology/p/1.0"]  # versions unchanged: nothing new to tag


def test_move_refused(tmp_path, root):
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    micro = _target(tmp_path, root, pin=False)
    roots = [root.path, micro.root]
    with pytest.raises(nf_repo.ReleaseRefused) as e:
        nf_repo.plan_move(root.repo, micro, "b", others=roots)
    assert any("add root@1.0" in i for i in e.value.issues)
    # unreleased edits, and a taken stem
    (tmp_path / "x").mkdir()
    micro = _target(tmp_path / "x", root)
    root.write("knowledge/b.nfx", root.doc(root.b, "b", "1.0", kind="knowledge", deps=[(root.a, "1.0")],
                                           nodes=[root.bn], rels=[(root.bn, root.an)], extra="edit"))
    root.commit("EDIT: b")
    (micro.root / "knowledge").mkdir()
    (micro.root / "knowledge/b.nfx").write_text("{}")
    with pytest.raises(nf_repo.ReleaseRefused) as e:
        nf_repo.plan_move(root.repo, micro, "b", others=[root.path, micro.root])
    assert any("unreleased edits since knowledge/b/1.0" in i for i in e.value.issues)
    assert any("exists in the target - pass --as" in i for i in e.value.issues)


def test_move_undone(tmp_path, root):
    # the target refuses after the source committed: both are put back
    _git(root.path, "config", "user.name", "T")
    _git(root.path, "config", "user.email", "t@example.org")
    micro = _target(tmp_path, root)
    head, micro_head = _git(root.path, "rev-parse", "HEAD"), _git(micro.root, "rev-parse", "HEAD")
    micro.check = lambda **_: nf_repo.Verdict(["refused"], [], [])
    with pytest.raises(nf_repo.ReleaseRefused):
        nf_repo.move(root.repo, micro, "b", others=[root.path, micro.root])
    assert _git(root.path, "rev-parse", "HEAD") == head and _git(micro.root, "rev-parse", "HEAD") == micro_head
    assert _git(root.path, "status", "--short") == "" and _git(micro.root, "status", "--short") == ""
    assert (root.path / "knowledge/b.nfx").is_file() and _git(micro.root, "tag", "-l") == ""


def test_rename_test():
    assert nf_repo.rename_test('x / "validators" / "a.py"\n', "a", "b") == 'x / "validators" / "b.py"\n'
    with pytest.raises(ValueError):
        nf_repo.rename_test("nothing\n", "a", "b")


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
