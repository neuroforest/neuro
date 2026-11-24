"""The tree registry - every `.nf` tree on this machine.

One file per machine, `~/.config/neuroforest/trees.toml`, maps a namespace nid to the
directory its tree lives in, the token beside it:

    format = 1

    [[tree]]
    nid = "0b0c…"
    token = "side"       # "" is the root namespace
    path = "/path/to/another/.nf"

It is what the `nf.*` tasks list and what an `@<token>` entry of `PLUGINS` is
looked up in. `PLUGINS` itself stays the *scope*: the trees one environment
may load (`plugins.effective_roots`). A tree is found by nid whatever its
directory is called today, so moving one (`move`) edits this file and nothing
else.

Written only here - `init`, `register`, `relocate`, `forget`, behind
`tree.init`, `tree.register`, `tree.move`, `tree.split` and `tree.forget`.
Other programs read the file with a
reader of their own, so the format is a contract: `format` changes only with
them in step. `NF_TREES` names another file, for tests and scratch work.

Not the namespace registry: that one maps a namespace to the
remote that owns it and is published; this one never leaves the machine.
"""
import dataclasses
import errno
import json
import os
import shutil
import subprocess
import tomllib
import uuid
from pathlib import Path

from neuro.base import nfx, plugins

FORMAT = 1
ENV_VAR = "NF_TREES"
ROOT_WORDS = ("", "root", "·")  # how the empty token is written in a command or a PLUGINS entry
STAGING = ".split"              # `<tree>.split`: a split staged beside the tree (nf_split.STAGING)
_HEADER = ("# The .nf trees on this machine: namespace nid → directory.\n"
           "# Written by tree.init, tree.register, tree.move and tree.split - not by hand.")


class RegistryError(ValueError):
    """The registry cannot take what was asked; `issues` lists why, one line each."""

    def __init__(self, issues):
        self.issues = [issues] if isinstance(issues, str) else list(issues)
        super().__init__("; ".join(self.issues))


@dataclasses.dataclass(frozen=True)
class Tree:
    nid: str
    token: str
    path: Path

    @property
    def present(self) -> bool:
        """The directory is there and still declares a namespace."""
        return (self.path / nfx.NAMESPACE_FILENAME).is_file()

    @property
    def word(self) -> str:
        return self.token or "root"


def registry_path() -> Path:
    """`$NF_TREES`, else `$XDG_CONFIG_HOME/neuroforest/trees.toml` - one per
    machine, whatever APP_NAME or ENV the process runs under."""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "neuroforest" / "trees.toml"


def read(path=None) -> list[Tree]:
    """The registered trees, in file order; none when the file does not exist."""
    path = Path(path) if path else registry_path()
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise RegistryError(f"{path}: {e}")
    if data.get("format") != FORMAT:
        raise RegistryError(f"{path}: format {data.get('format')!r}, this code reads format {FORMAT}")
    trees = []
    for row in data.get("tree", []):
        try:
            trees.append(Tree(str(row["nid"]), str(row.get("token", "")), Path(row["path"])))
        except KeyError as e:
            raise RegistryError(f"{path}: a tree without {e}")
    return trees


def write(trees, path=None) -> None:
    path = Path(path) if path else registry_path()
    lines = [_HEADER, f"format = {FORMAT}", ""]
    for t in trees:
        lines += ["[[tree]]", f"nid = {_s(t.nid)}", f"token = {_s(t.token)}", f"path = {_s(str(t.path))}", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines))
    os.replace(tmp, path)


def _s(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a TOML basic string


def declared(root) -> nfx.Nfx:
    """The namespace declaration of the tree at `root`."""
    root = Path(root)
    if not plugins.is_consolidated(root):
        raise RegistryError(f"{root}: a tree is a directory named {plugins.NF_DIRNAME}")
    path = root / nfx.NAMESPACE_FILENAME
    if not path.is_file():
        raise RegistryError(f"{root}: no {nfx.NAMESPACE_FILENAME} - not a tree")
    doc = nfx.read(path)
    if not doc.is_namespace or not doc.nid:
        raise RegistryError(f"{path}: not a namespace declaration with a nid")
    return doc


def by_token(token, trees=None) -> Tree | None:
    """The registered tree of that token (`root`, `·` or nothing: the empty
    one), a present one before an absent one; None when none or several."""
    want = "" if token in ROOT_WORDS else token
    found = [t for t in (read() if trees is None else trees) if t.token == want]
    found = [t for t in found if t.present] or found
    return found[0] if len(found) == 1 else None


def find(key, trees=None) -> Tree | None:
    """A registered tree by nid, by path, or by token."""
    trees = read() if trees is None else trees
    path = Path(key).expanduser().resolve() if key not in ROOT_WORDS else None
    for t in trees:
        if t.nid == key or (path is not None and t.path == path):
            return t
    return by_token(key, trees)


def _put(new: Tree, replace=False, path=None) -> Tree:
    """Write `new` into the registry: in place of the line of its directory or
    of its nid, else at the end."""
    trees, kept, at = read(path), [], None
    for i, t in enumerate(trees):
        if t.path == new.path:  # this directory's own line, whatever it said before
            at = len(kept) if at is None else at
        elif t.nid == new.nid:
            if t.present and not replace:
                raise RegistryError(f"namespace {new.nid} is registered at {t.path}, another checkout of it - "
                                    f"`tree.move` relocates a tree; --replace points the registry here instead")
            at = len(kept) if at is None else at
        elif t.token == new.token and t.present:
            raise RegistryError(f"the token {new.word!r} is taken by the tree at {t.path}")
        else:
            kept.append(t)
    kept.insert(len(kept) if at is None else at, new)
    write(kept, path)
    return new


def register(root, replace=False, path=None) -> Tree:
    """Record the tree at `root`: its nid and token as it declares them now.
    Idempotent. Refused when the namespace is registered at another directory
    that still holds it (unless `replace`), or the token belongs to another
    tree that is present."""
    root = Path(root).expanduser().resolve()
    doc = declared(root)
    return _put(Tree(doc.nid, doc.namespace or "", root), replace, path)


def forget(key, path=None) -> Tree | None:
    """Drop one line (by nid, path or token). Touches no directory."""
    trees = read(path)
    gone = find(key, trees)
    if gone is not None:
        write([t for t in trees if t != gone], path)
    return gone


# ---- tree.init ------------------------------------------------------------------------------


def init(root, token, name="", description="", pins=(), branch="master") -> nfx.Nfx:
    """An empty tree at `root`: the directory, a repository (its own, unless
    `root` already lies inside a work tree - a project's `.nf`), and a
    `namespace.nfx` with a fresh nid declaring `token` and pinning `pins`
    (`(nid, version)` of other namespaces). No commit, no hooks, no registry
    line: the caller installs the hooks first so the first commit runs them."""
    root = Path(root).expanduser()
    root = root.parent.resolve() / root.name
    token = "" if token in ROOT_WORDS else token
    doc = nfx.Nfx(type=nfx.NAMESPACE_TYPE, nid=str(uuid.uuid4()), version="1.0", name=name or token or "Root",
                  description=description, namespace=token, dependencies=tuple(pins))
    issues = list(nfx.namespace_issues(doc))
    if not plugins.is_consolidated(root):
        issues.append(f"{root}: a tree is a directory named {plugins.NF_DIRNAME}")
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        issues.append(f"{root} exists and is not empty")
    inside = _enclosing_tree(root)
    if inside is not None:
        issues.append(f"{root} lies inside the tree {inside}")
    taken = by_token(token)
    if taken is not None and taken.present:
        issues.append(f"the token {taken.word!r} is taken by the tree at {taken.path}")
    if issues:
        raise RegistryError(issues)
    root.mkdir(parents=True, exist_ok=True)
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode:
        r = _git(root, "init", "-q", "-b", branch)
        if r.returncode:
            raise RuntimeError(f"git init {root}: {r.stderr.strip()}")
    nfx.write(root / nfx.NAMESPACE_FILENAME, doc)
    return doc


def _enclosing_tree(path: Path) -> Path | None:
    return next((d for d in path.parents if (d / nfx.NAMESPACE_FILENAME).is_file()), None)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


# ---- tree.move ------------------------------------------------------------------------------


def move(root, to, path=None) -> Tree:
    """Relocate the tree at `root` to `to` and rewrite its registry line
    Leaves no commit: pins are by namespace nid and the
    hook shims call the wrapper named in `git config nf.runner`, so nothing
    inside the repository holds its own path. Across filesystems: copy,
    `git fsck` the copy, then remove the original."""
    root = Path(root).expanduser().resolve()
    to = Path(to).expanduser()
    to = to.parent.resolve() / to.name
    doc = declared(root)
    issues = []
    if not plugins.is_consolidated(to):
        issues.append(f"{to}: the destination must be named {plugins.NF_DIRNAME}")
    if to.exists():
        issues.append(f"{to} exists")
    inside = _enclosing_tree(to)
    if inside is not None:
        issues.append(f"{to} lies inside the tree {inside}")
    staged = root.parent / (root.name + STAGING)
    if staged.exists():
        issues.append(f"a split is staged in {staged} - swap it or remove it first")
    top = _git(root, "rev-parse", "--show-toplevel").stdout.strip()
    if not top or Path(top).resolve() != root:
        issues.append(f"{root} is part of the repository {top or '?'} - move that, then `tree.register`")
    elif not (root / ".git").is_dir():
        issues.append(f"{root} is a linked worktree - `git worktree move` it, then `tree.register`")
    elif _git(root, "status", "--porcelain").stdout.strip():
        issues.append(f"{root} has uncommitted work")
    if issues:
        raise RegistryError(issues)
    to.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(root, to)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        shutil.copytree(root, to, symlinks=True)
        r = _git(to, "fsck", "--no-dangling")
        if r.returncode:
            shutil.rmtree(to)
            raise RuntimeError(f"the copy in {to} failed git fsck and was removed; {root} is untouched: "
                               f"{(r.stderr or r.stdout).strip()}")
        shutil.rmtree(root)
    return _put(Tree(doc.nid, doc.namespace or "", to), replace=True, path=path)
