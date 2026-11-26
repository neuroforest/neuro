"""
Copy a legacy plugins root into a consolidated `.nf` root.

`plan_import` reads the legacy root through `NfxIndex` and returns a
`Mapping`: every file the `.nf` root will hold, with its bytes, plus what was
left behind and what stops the copy. Nothing is written by planning. The
rules:

- a module goes to `ontology/` or `knowledge/` by its own `type` field, under
  its file stem - the local name, which may not repeat (the index refuses it);
- its `name` becomes that stem (name = stem), rewritten in
  place so the rest of the file keeps its bytes;
- a module nested in a parent plugin gets that parent as an explicit pin,
  since the `.nf` layout has no nesting to imply it;
- `<plugin>/validators.py` becomes `validators/<stem>.py`, `<stem>` being the
  one ontology of the plugin; its sha256 must already equal that module's
  `hash` - the copy keeps the bytes, so the hash rule holds or the source is
  wrong and must be rehashed there;
- `<plugin>/test_validators.py` becomes `tests/test_<stem>.py`, its one path
  line rewritten to load `validators/<stem>.py`;
- `namespace.nfx` is generated: the empty token, name *Root*, pinning the
  parent (the app's builtin namespace);
- the root's `ruff.toml` and `.gitignore` are copied; `.scripts/` is not -
  hooks come from `neuro`;
- any other file is reported as unmapped, which blocks the copy.

`stage` writes a mapping into an empty directory, `diff` compares it with an
existing root, `sync` makes that root equal to it (writing what differs and
removing what the mapping no longer holds, inside the managed paths only),
and `verify` checks a staged root against its source: same modules, same
nids, same versions, the hash rule, every pin satisfied. Re-running the whole
cycle is idempotent; its diff doubles as the drift report of the parallel
period (C5).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from neuro.base import nfx, plugins
from neuro.base.index import NfxIndex

_MODULE_TYPES = ("ontology", "knowledge")
_TEST = "test_validators.py"
_COPIED_TOP_FILES = ("ruff.toml", ".gitignore")
_SKIPPED_DIRS = {".git", ".scripts", "__pycache__", ".pytest_cache", ".ruff_cache"}
_MANAGED_DIRS = ("ontology", "knowledge", "validators", "tests")
_MANAGED_TOP_FILES = (nfx.NAMESPACE_FILENAME, *_COPIED_TOP_FILES)

ROOT_NAME = "Root"
ROOT_DESCRIPTION = "The root namespace: the modules of the legacy plugins repo, imported"

_NFX_LINE = re.compile(r'^(?P<var>_\w+)_NFX = Path\(__file__\)\.with_name\("(?P<stem>[^"]+)\.nfx"\)$', re.M)


@dataclass(frozen=True)
class Move:
    """One file of the `.nf` root. `src` is None for a generated file; `rel`
    is the path inside the root. A module move carries its nid, the tag C2
    cuts for it and the `name` it had in the source (legacy tags and
    messages use it); `note` says what changed on the way, if anything."""
    src: Path | None
    rel: Path
    content: bytes
    nid: str = ""
    tag: str = ""
    note: str = ""
    name: str = ""


@dataclass
class Mapping:
    src_root: Path
    moves: list[Move] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def modules(self) -> list[Move]:
        return [m for m in self.moves if m.nid]


def tag_for(kind: str, stem: str, version: str) -> str:
    """The annotated tag a module is released under."""
    return f"{kind}/{stem.lower()}/{version}"


def namespace_tag(token: str | None, version: str) -> str:
    """The annotated tag a root's declaration is released under: `namespace/<token>/<version>`
    - the token because one git repository may hold several trees - and
    `namespace/<version>` for the tokenless root."""
    return f"namespace/{token}/{version}" if token else f"namespace/{version}"


def namespace_doc(nid: str, parent_nid: str, parent_version: str, version: str = "1.0") -> nfx.Nfx:
    return nfx.Nfx(
        type=nfx.NAMESPACE_TYPE,
        nid=nid,
        version=version,
        name=ROOT_NAME,
        description=ROOT_DESCRIPTION,
        namespace="",
        dependencies=((parent_nid, parent_version),),
    )


def rename_to_stem(content: bytes, stem: str) -> tuple[bytes, str]:
    """Set the document's top-level `name` to `stem`, touching only that value.
    Returns the new bytes and the old name ("" when it already was `stem`).
    The top-level key precedes `nodes` in every document, so the first
    `"name": …` pair is it; the result must parse to the same document with
    only `name` changed, else ValueError."""
    doc = json.loads(content)
    old = doc.get("name")
    if old == stem:
        return content, ""
    text = content.decode()
    if old is None:
        raise ValueError("declares no name")
    pair = re.compile(r'"name"(\s*):(\s*)' + re.escape(json.dumps(old, ensure_ascii=False)))
    new, count = pair.subn(lambda m: f'"name"{m[1]}:{m[2]}{json.dumps(stem)}', text, count=1)
    if count != 1 or json.loads(new) != {**doc, "name": stem}:
        raise ValueError(f"cannot rewrite name {old!r} in place")
    return new.encode(), old


def rewrite_test(text: str, stem: str) -> str:
    """Point a legacy `test_validators.py` at `validators/<stem>.py`.

    The legacy tests locate their validators through the sibling `.nfx`
    (`Path(__file__).with_name(...)` + `plugins.load_plugin_at`); in a `.nf`
    root neither the sibling nor the heuristic exists. Raises ValueError when
    the file does not have exactly that shape - a test is never copied
    half-rewritten.
    """
    found = list(_NFX_LINE.finditer(text))
    if len(found) != 1:
        raise ValueError(f"expected one `_X_NFX = Path(__file__).with_name(...)` line, found {len(found)}")
    m = found[0]
    if m["stem"] != stem:
        raise ValueError(f"locates {m['stem']}.nfx, not {stem}.nfx")
    var = m["var"]
    load = f"plugins.load_plugin_at({var}_NFX)"
    if text.count(load) != 1:
        raise ValueError(f"expected one `{load}`")
    text = text.replace(m[0], f'{var}_VALIDATORS = Path(__file__).parents[1] / "validators" / "{stem}.py"')
    text = text.replace(load, f"plugins.load_validators_file({var}_VALIDATORS)")
    if f"{var}_NFX" in text:
        raise ValueError(f"{var}_NFX is used beyond locating the validators")
    return text


def plan_import(src_root, namespace: nfx.Nfx, type_of=None) -> Mapping:
    """Map the legacy root `src_root` onto the `.nf` layout. `namespace` is
    the declaration to write (see `namespace_doc`). `type_of(nid)` places a
    module that declares no `type` - history predating the field
    (`nf_history`); the file's bytes are kept as they were."""
    src_root = Path(src_root).resolve()
    out = Mapping(src_root=src_root)
    if plugins.is_consolidated(src_root):
        out.issues.append(f"{src_root} is already a .nf root")
        return out
    idx = NfxIndex(src_root)
    entries = idx.entries()
    by_nid = {e.nid: e for e in entries}
    claimed: set[Path] = set()

    out.moves.append(Move(None, Path(nfx.NAMESPACE_FILENAME), nfx.dumps(namespace).encode()))

    kinds = {e.nid: e.type or (type_of(e.nid) if type_of else "") for e in entries}
    for e in sorted(entries, key=lambda e: (kinds[e.nid], e.path.stem.lower())):
        claimed.add(e.path)
        kind = kinds[e.nid]
        if kind not in _MODULE_TYPES:
            out.issues.append(f"{e.path.relative_to(src_root)}: type {kind!r} has no place in a .nf root")
            continue
        content = e.path.read_bytes()
        doc = nfx.read(e.path)
        notes = []
        parent = by_nid.get(e.implicit_parent_nid) if e.implicit_parent_nid else None
        if parent is not None and parent.nid not in {n for n, _ in doc.dependencies}:
            doc = replace(doc, dependencies=(*doc.dependencies, (parent.nid, parent.version)))
            content = nfx.dumps(doc).encode()
            notes.append(f"pins parent {parent.path.stem}@{parent.version}")
        source_name = doc.name or ""
        try:
            content, old = rename_to_stem(content, e.path.stem)
        except ValueError as err:
            out.issues.append(f"{e.path.relative_to(src_root)}: {err}")
            continue
        if old:
            notes.append(f"name {old!r} → {e.path.stem!r}")
        out.moves.append(Move(
            e.path, Path(kind) / f"{e.path.stem}.nfx", content,
            nid=e.nid, tag=tag_for(kind, e.path.stem, doc.version), note="; ".join(notes),
            name=source_name,
        ))

    by_validators: dict[Path, list] = {}
    for e in entries:
        if e.validators_path is not None and e.validators_path.is_file():
            by_validators.setdefault(e.validators_path, []).append(e)
        elif kinds[e.nid] == "ontology" and nfx.read(e.path).hash:
            out.issues.append(f"{e.path.relative_to(src_root)}: carries a hash but has no validators")
    for vpath, group in sorted(by_validators.items()):
        rel = vpath.relative_to(src_root)
        test = vpath.with_name(_TEST)
        claimed.update((vpath, test))
        owners = [e for e in group if kinds[e.nid] == "ontology"]
        if len(owners) != 1:
            out.issues.append(f"{rel}: needs exactly one ontology in its plugin to own it, found {len(owners)}")
            continue
        owner = owners[0]
        stem = owner.path.stem
        content = vpath.read_bytes()
        if hashlib.sha256(content).hexdigest() != nfx.read(owner.path).hash:
            out.issues.append(f"{rel}: sha256 differs from {owner.path.name}'s hash - `ontology.rehash` the source")
        out.moves.append(Move(vpath, Path("validators") / f"{stem}.py", content, note=f"of {stem}"))
        if test.is_file():
            try:
                text = rewrite_test(test.read_text(), stem)
            except ValueError as err:
                out.issues.append(f"{test.relative_to(src_root)}: {err}")
                continue
            out.moves.append(Move(test, Path("tests") / f"test_{stem}.py", text.encode(), note="path rewritten"))

    for name in _COPIED_TOP_FILES:
        path = src_root / name
        if path.is_file():
            claimed.add(path)
            out.moves.append(Move(path, Path(name), path.read_bytes()))

    for path in sorted(_files(src_root)):
        if path not in claimed:
            out.issues.append(f"{path.relative_to(src_root)}: unmapped")
    scripts = src_root / ".scripts"
    if scripts.is_dir():
        out.skipped.extend(sorted(p for p in scripts.iterdir() if p.is_file()))
    return out


def _files(root: Path):
    """Every file under `root` an import must account for: caches, `.git`
    and `.scripts/` aside (the latter is listed as skipped by the caller)."""
    for path in root.rglob("*"):
        if any(part in _SKIPPED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if path.is_file() and path.suffix != ".pyc":
            yield path


def _managed(root: Path) -> set[Path]:
    """The paths of `root` an import owns, relative: the four kind dirs and
    the top files it writes. `.git`, `.githooks` and anything else stay."""
    found = set()
    for name in _MANAGED_TOP_FILES:
        if (root / name).is_file():
            found.add(Path(name))
    for d in _MANAGED_DIRS:
        base = root / d
        if base.is_dir():
            found.update(p.relative_to(root) for p in base.rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts)
    return found


def stage(mapping: Mapping, root) -> None:
    """Write `mapping` into `root` (expected empty)."""
    root = Path(root)
    for m in mapping.moves:
        dst = root / m.rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(m.content)


def diff(mapping: Mapping, root) -> dict[str, list[Path]]:
    """Compare `mapping` with an existing root: `new`, `changed`, `same`, and
    `stale` (held by the root, gone from the mapping). A missing root is all
    `new`."""
    root = Path(root)
    out: dict[str, list[Path]] = {"new": [], "changed": [], "same": [], "stale": []}
    planned = set()
    for m in mapping.moves:
        planned.add(m.rel)
        dst = root / m.rel
        if not dst.is_file():
            out["new"].append(m.rel)
        elif dst.read_bytes() != m.content:
            out["changed"].append(m.rel)
        else:
            out["same"].append(m.rel)
    if root.is_dir():
        out["stale"] = sorted(_managed(root) - planned)
    return out


def sync(mapping: Mapping, root) -> dict[str, list[Path]]:
    """Make `root` hold exactly `mapping` in its managed paths; returns the
    diff that was applied."""
    root = Path(root)
    delta = diff(mapping, root)
    contents = {m.rel: m.content for m in mapping.moves}
    for rel in (*delta["new"], *delta["changed"]):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(contents[rel])
    for rel in delta["stale"]:
        (root / rel).unlink()
    return delta


def verify(staged, src_root, *base_trees) -> list[str]:
    """Check the `.nf` root `staged` against the legacy `src_root`.

    `base_trees` are the trees the staged one stands on (the app's builtin
    `.nf`, which holds the metaontology its modules pin). Returns problems;
    empty means the copy indexes the identical module and nid set at the same
    versions, keeps the hash rule and satisfies every pin.
    """
    staged = Path(staged).resolve()
    issues = []
    src = {e.nid: e for e in NfxIndex(src_root).entries()}
    idx = NfxIndex(*base_trees, staged)
    dst = {e.nid: e for e in idx.entries() if e.tree == staged}
    for nid in sorted(src.keys() - dst.keys()):
        issues.append(f"{src[nid].path.name}: missing from the copy")
    for nid in sorted(dst.keys() - src.keys()):
        issues.append(f"{dst[nid].path.name}: not in the source")
    for nid in sorted(src.keys() & dst.keys()):
        s, d = src[nid], dst[nid]
        if (s.path.stem, s.type, s.version) != (d.path.stem, d.type, d.version):
            issues.append(f"{d.path.name}: {s.path.stem}/{s.type}@{s.version} became "
                          f"{d.path.stem}/{d.type}@{d.version}")
        if d.name != d.path.stem:
            issues.append(f"{d.path.name}: name {d.name!r} is not its stem")
        vpath = plugins.validators_path_for(d.path, idx.trees)
        doc_hash = nfx.read(d.path).hash
        if vpath is not None and vpath.is_file():
            if hashlib.sha256(vpath.read_bytes()).hexdigest() != doc_hash:
                issues.append(f"{d.path.name}: hash does not match {vpath.name}")
        elif doc_hash:
            issues.append(f"{d.path.name}: carries a hash but has no validators")
        for err in idx.check_dependency_versions(d.path):
            issues.append(f"{d.path.name}: {err}")
    return issues
