"""
Unit tests for neuro.base.nf_trees - the machine's registry of `.nf` trees.
"""

import pytest

from neuro.base import nf_trees, nfx, plugins
from tests.base.test_nf_repo import _git, _Root

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    path = tmp_path / "config" / "trees.toml"
    monkeypatch.setenv(nf_trees.ENV_VAR, str(path))
    return path


def _tree(path, token, nid=None):
    import uuid

    path.mkdir(parents=True)
    nfx.write(path / nfx.NAMESPACE_FILENAME, nfx.Nfx(type=nfx.NAMESPACE_TYPE, nid=nid or str(uuid.uuid4()),
                                                    version="1.0", name=token or "Root", namespace=token))
    return path


def test_registry_path(registry, monkeypatch, tmp_path):
    assert nf_trees.registry_path() == registry
    monkeypatch.delenv(nf_trees.ENV_VAR)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert nf_trees.registry_path() == tmp_path / "nf" / "trees.toml"


def test_read(registry, tmp_path):
    assert nf_trees.read() == []
    trees = [nf_trees.Tree("n1", "", tmp_path / ".nf"), nf_trees.Tree("n2", "kb", tmp_path / 'a "b"' / ".nf")]
    nf_trees.write(trees)
    assert nf_trees.read() == trees
    assert "format = 1" in registry.read_text()
    registry.write_text("format = 2\n")
    with pytest.raises(nf_trees.RegistryError, match="format 2"):
        nf_trees.read()


def test_register(tmp_path):
    a = _tree(tmp_path / "a" / ".nf", "")
    b = _tree(tmp_path / "b" / ".nf", "kb")
    ta, tb = nf_trees.register(a), nf_trees.register(b)
    assert nf_trees.read() == [ta, tb] and nf_trees.register(a) == ta and nf_trees.read() == [ta, tb]
    assert nf_trees.by_token("root") == ta and nf_trees.find("kb") == tb and nf_trees.find(tb.nid) == tb
    # another checkout of a registered namespace, and a token that is taken
    clone = _tree(tmp_path / "c" / ".nf", "kb", nid=tb.nid)
    with pytest.raises(nf_trees.RegistryError, match="another checkout"):
        nf_trees.register(clone)
    with pytest.raises(nf_trees.RegistryError, match="taken"):
        nf_trees.register(_tree(tmp_path / "d" / ".nf", "kb"))
    assert nf_trees.register(clone, replace=True).path == clone and len(nf_trees.read()) == 2
    # a tree whose directory is gone gives way without --replace; its line keeps its place
    (clone / nfx.NAMESPACE_FILENAME).unlink()
    assert nf_trees.register(b) == tb and nf_trees.read() == [ta, tb]
    with pytest.raises(nf_trees.RegistryError, match="named .nf"):
        nf_trees.register(tmp_path)
    assert nf_trees.forget("kb") == tb and nf_trees.read() == [ta] and nf_trees.forget("kb") is None


def test_init(tmp_path):
    import uuid

    root, pin = tmp_path / "kb" / ".nf", str(uuid.uuid4())
    doc = nf_trees.init(root, "kb", pins=[(pin, "1.0")])
    assert (root / ".git").is_dir() and nfx.read(root / nfx.NAMESPACE_FILENAME) == doc
    assert (doc.namespace, doc.name, doc.version, doc.dependencies) == ("kb", "kb", "1.0", ((pin, "1.0"),))
    assert nf_trees.read() == []  # the caller registers, after the hooks and the first commit
    with pytest.raises(nf_trees.RegistryError) as e:
        nf_trees.init(root / "x" / ".nf", "Not A Token")
    assert len(e.value.issues) == 2 and "inside the tree" in e.value.issues[1]
    with pytest.raises(nf_trees.RegistryError, match="not empty"):
        nf_trees.init(root, "other")
    nf_trees.register(root)
    with pytest.raises(nf_trees.RegistryError, match="taken"):
        nf_trees.init(tmp_path / "kb2" / ".nf", "kb")
    # inside a project's work tree the tree joins that repository
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q")
    nf_trees.init(project / ".nf", "proj")
    assert not (project / ".nf" / ".git").exists()


def test_move(tmp_path):
    root = _Root(tmp_path / ".nf")
    nf_trees.register(root.path)
    to = tmp_path / "there" / ".nf"
    (root.path / "ruff.toml").write_text("")
    with pytest.raises(nf_trees.RegistryError) as e:
        nf_trees.move(root.path, tmp_path / "there" / "nf")
    assert ["must be named" in e.value.issues[0], "uncommitted" in e.value.issues[1]] == [True, True]
    (root.path / "ruff.toml").unlink()
    (tmp_path / ".nf.split").mkdir()
    with pytest.raises(nf_trees.RegistryError, match="split is staged"):
        nf_trees.move(root.path, to)
    (tmp_path / ".nf.split").rmdir()
    with pytest.raises(nf_trees.RegistryError, match="inside the tree"):
        nf_trees.move(root.path, root.path / "x" / ".nf")
    head = root.repo.rev("HEAD")
    moved = nf_trees.move(root.path, to)
    assert not root.path.exists() and moved.path == to and nf_trees.read() == [moved]
    assert _git(to, "rev-parse", "HEAD").strip() == head and _git(to, "status", "--porcelain") == ""


def test_scope(tmp_path, monkeypatch):
    a = _tree(tmp_path / "a" / ".nf", "")
    b = _tree(tmp_path / "b" / ".nf", "kb")
    nf_trees.register(a)
    nf_trees.register(b)
    monkeypatch.setenv("APP_DIR", str(tmp_path))
    monkeypatch.setenv("PLUGINS", f"a/.nf:@kb:@root:@gone:{tmp_path}/nowhere")
    assert plugins.effective_roots() == [a, b]  # `@root` names a tree the path already did
    assert plugins.missing_roots() == ["@gone", f"{tmp_path}/nowhere"]
    # the scope follows a tree that moves; a path entry does not
    _git(b, "init", "-q", "-b", "master")
    _git(b, "add", ".")
    _git(b, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "ADD: namespace")
    nf_trees.move(b, tmp_path / "c" / ".nf")
    assert plugins.effective_roots() == [a, tmp_path / "c" / ".nf"]


def test_track_notes(tmp_path):
    from neuro.base import nf_repo

    root = _Root(tmp_path / ".nf")
    assert root.repo.track_notes() == []
    _git(root.path, "remote", "add", "mirror", "ssh://example.org/x.git")
    assert root.repo.track_notes() == ["mirror"] and root.repo.track_notes() == []
    fetch = _git(root.path, "config", "--get-all", "remote.mirror.fetch").splitlines()
    assert fetch == ["+refs/heads/*:refs/remotes/mirror/*", f"+{nf_repo.NOTES_REF}:{nf_repo.NOTES_REF}"]
