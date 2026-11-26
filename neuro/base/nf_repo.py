"""
A `.nf` root's git hooks.

One rule set for every document of the root - ontology, knowledge and
`namespace.nfx` alike. `Repo.check` is the pre-commit verdict: the *new* tree
(the index, or a commit when replaying history) is written out as a scratch
`.nf`, indexed beside the other roots, and judged against the *base* (HEAD, or
the commit's parent) and the release tags. `Repo.tag` is post-commit: one
annotated tag per document whose version has none yet. `nfx` stays the
git-free format layer; everything that reads a repository lives here.

Versioning: every committed change to
a document is a release. A commit that changes one must carry the next version
after its latest tag - there is no unreleased edit; only a module's test file
may change alone. The commit then carries its whole re-pin closure:
every pin on it inside the root updated in the same commit. Dependants inside
the root are re-validated whenever something they depend on changes, so a
document that drops a node another one still references is refused at its own
commit. Pins into other roots are checked only on documents the commit
touches; a stale one elsewhere is the staleness report's business (013 P9).

A root is either a repository of its own (`~/.nf`) or a directory inside a
project repository (`app-nf/.nf`): `Repo` finds the toplevel and works on the
root's subtree only.
"""

import dataclasses
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

from neuro.base import nf_events, nf_import, nfx, plugins
from neuro.base.index import NfxIndex
from neuro.base.nf_history import _pins, is_repin
from neuro.utils import exceptions

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HOOKS = ("pre-commit", "post-commit")
SHIM_DIR = ".githooks"
NOTES_REF = "refs/notes/nf-origin"  # per commit: the sha and namespace it was made as, before a split or a reconcile
_SENTINEL = "# nf hook"
_GIT_PATH_VARS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")
_LABELS_SPLIT = re.compile(r'"labels"\s*:\s*\[[^\]]*\n')


def version_key(version: str) -> tuple[int, ...] | None:
    """`"1.4"` → `(1, 4)`; None for anything that is not two dotted integers."""
    parts = version.split(".")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1])


def next_versions(version: str) -> set[str]:
    major, minor = version_key(version)
    return {f"{major}.{minor + 1}", f"{major + 1}.0"}


def series_of(rel: Path) -> tuple[str, str] | None:
    """The tag series a root-relative `.nfx` path belongs to: `(kind, stem)` for
    `ontology/<stem>.nfx` / `knowledge/<stem>.nfx`, `("namespace", "")` for the
    declaration, None for anything else. The kind is the subdir - the index
    holds it equal to the `type` (the metaontology aside).
    Inside one root the declaration's series has no stem; its tag carries the
    root's token (`Repo.tag_of`), since one git repository may hold several roots."""
    rel = Path(rel)
    if rel == Path(nfx.NAMESPACE_FILENAME):
        return NAMESPACE_SERIES
    if rel.suffix == ".nfx" and len(rel.parts) == 2 and rel.parts[0] in plugins._KIND_SUBDIRS:
        return rel.parts[0], rel.stem.lower()
    return None


NAMESPACE_SERIES = ("namespace", "")


def tag_name(series: tuple[str, str], version: str, token: str = "") -> str:
    """The tag of `series` at `version`. A namespace series names its root by
    `token`, or by the stem `parse_tag` read out of such a tag."""
    kind, stem = series
    if kind == "namespace":
        return nf_import.namespace_tag(token or stem, version)
    return nf_import.tag_for(kind, stem, version)


def parse_tag(name: str) -> tuple[tuple[str, str], str] | None:
    """`(series, version)` of a release tag; a namespace tag's stem is its root's token."""
    parts = name.split("/")
    if len(parts) == 2 and parts[0] == "namespace":
        return NAMESPACE_SERIES, parts[1]
    if len(parts) == 3 and parts[0] == "namespace":
        return ("namespace", parts[1]), parts[2]
    if len(parts) == 3 and parts[0] in plugins._KIND_SUBDIRS:
        return (parts[0], parts[1]), parts[2]
    return None


def document_failures(idx, path) -> list[str]:
    """Defects of one `.nfx` document on its own terms: structure, references
    resolved through `idx`, canonical format. Shared by the hook, `ontology.test`
    and `tree.import`; must run before an import, since MERGE collapses duplicates."""
    raw = json.loads(Path(path).read_text())
    doc = nfx.Nfx.from_dict(raw)

    def resolve(nid):
        dep_path = idx.resolve(nid)
        return nfx.read(dep_path) if dep_path else None

    try:
        tree = nfx.NfxTree(doc, resolve)
    except exceptions.NfxCycle as e:
        return [f"dependency cycle {' → '.join(e.args[0])}"]
    report = nfx.validate(doc, dependency_nids=tree.all_node_nids(scope="dependencies"))
    lint = nfx.lint_format(raw)

    failures = []
    for bad in report["invalid_nids"]:
        failures.append(f"invalid nid {bad} (not UUID v4)")
    for r in report["unresolved"]:
        failures.append(f"unresolved {r.get('type', '?')} {r['from']} → {r['to']}")
    for r in report["foreign"]:
        failures.append(f"foreign {r.get('type', '?')} {r['from']} → {r['to']} (both endpoints external)")
    for nid in report["duplicate_nids"]:
        failures.append(f"duplicate node nid {nid}")
    for r in report["duplicate_relationships"]:
        failures.append(f"duplicate {r.get('type', '?')} {r['from']} → {r['to']}")
    for f in report["missing_required"]:
        failures.append(f"missing required top-level field {f!r}")
    if report["invalid_type"]:
        failures.append(f"type {report['invalid_type']!r} not in {list(nfx.ALLOWED_TYPES)}")
    if report["untaggable_name"]:
        failures.append(
            f"name {report['untaggable_name']!r} cannot form the release tag "
            f"{report['untaggable_name'].lower()}/{doc.version} - git rejects the ref"
        )
    for u in lint["unknown_keys"]:
        failures.append(f"{u['where']} has unknown keys {u['keys']}")
    for ko in lint["key_order"]:
        failures.append(f"{ko['where']} key order {ko['keys']} not canonical")
    for f in lint["empty"]:
        failures.append(f"{f!r} is empty - omit the key instead")
    return failures


def namespace_failures(idx, path) -> list[str]:
    """Defects of a root's `namespace.nfx`: its form, and its pins on the
    namespaces `idx` knows. A declaration has no schema - this is all of it."""
    raw = json.loads(Path(path).read_text())
    ns = nfx.Nfx.from_dict(raw)
    failures = [f"missing required top-level field {f!r}" for f in nfx.missing_fields(ns)]
    failures += nfx.namespace_issues(ns)
    lint = nfx.lint_format(raw)
    failures += [f"{k['where']} key order {k['keys']} not canonical" for k in lint["key_order"]]
    failures += [f"{u['where']} has unknown keys {u['keys']}" for u in lint["unknown_keys"]]
    declared = {n.nid: n for n in idx.namespaces()}
    for dep, pin in ns.dependencies:
        if dep not in declared:
            failures.append(f"pins namespace {dep}@{pin}, which no root declares")
        elif declared[dep].version != pin:
            failures.append(f"pins {declared[dep].token or '∅'}@{pin}, it is {declared[dep].version}")
    return failures


def module_test_path(path, roots) -> Path | None:
    """The pytest file of a module, if it has one: `tests/test_<stem>.py` in a
    `.nf` root, `test_validators.py` beside the document in a legacy one."""
    path = Path(path)
    root = plugins.registry_root_of(path, roots)
    if root is not None and plugins.is_consolidated(root):
        candidate = root / "tests" / f"test_{path.stem}.py"
    else:
        candidate = path.parent / "test_validators.py"
    return candidate if candidate.is_file() else None


def _is_released(root) -> bool:
    """Whether the root at `root` releases its documents - true unless its
    declaration says `"released": false`. Read raw: a malformed declaration is
    reported by the checks, and until it parses the release rule stays on."""
    path = Path(root) / nfx.NAMESPACE_FILENAME
    try:
        return json.loads(path.read_text()).get("released") is not False
    except (OSError, ValueError, AttributeError):
        return True


def _labels_split(text: str) -> list[int]:
    return [text[:m.start()].count("\n") + 1 for m in _LABELS_SPLIT.finditer(text)]


@dataclasses.dataclass
class Step:
    """One document a release writes."""
    rel: Path
    name: str
    type: str
    old: str
    new: str
    repins: list[str]
    seed: bool
    carries: bool        # it also releases edits made since its last tag
    text: str            # the document as written

    def line(self) -> str:
        """The commit-body line for a cascaded document."""
        tail = f"re-pin {', '.join(self.repins)}" if self.repins else "re-pin"
        return f"{self.name} {self.old} → {self.new} ({tail}{'; carries unreleased edits' if self.carries else ''})"


def release_subject(seeds) -> str:
    """`RELEASE: <type> <name> <version>[, …]` for the documents a release was
    asked for. The type is written once when they share it, and not at all
    where it would only repeat the name: `RELEASE: metaontology 3.3`."""
    kinds = {s.type for s in seeds}
    kind = kinds.pop() if len(kinds) == 1 else ""
    if all(s.name == kind for s in seeds):
        kind = ""
    return "RELEASE: " + (f"{kind} " if kind else "") + ", ".join(f"{s.name} {s.new}" for s in seeds)


@dataclasses.dataclass
class RenamePlan:
    kind: str
    old: str
    new: str
    nid: str
    files: list[tuple[Path, Path]]  # root-relative, the .nfx first
    tags: list[tuple[str, str]]     # old tag → new tag, oldest first

    @property
    def event(self) -> nf_events.Rename:
        return nf_events.Rename(self.kind, self.old, self.new)


def rename_test(text: str, old: str, new: str) -> str:
    """Point a module's test at `validators/<new>.py`: the one line `tree.import`
    wrote (`… / "validators" / "<old>.py"`) - exactly one, else ValueError."""
    line = f'"{plugins._VALIDATORS_DIR}" / "{old}.py"'
    if text.count(line) != 1:
        raise ValueError(f"expected one `{line}` in the test, found {text.count(line)}")
    return text.replace(line, f'"{plugins._VALIDATORS_DIR}" / "{new}.py"')


class ReleaseRefused(Exception):
    def __init__(self, issues):
        super().__init__(f"{len(issues)} issue(s)")
        self.issues = list(issues)


@dataclasses.dataclass
class Verdict:
    issues: list[str]
    checked: list[str]   # root-relative paths validated in full
    released: list[str]  # tags the commit will make (changed versions)


class Repo:
    """The git side of one `.nf` root."""

    def __init__(self, root):
        self._env = os.environ.copy()  # a hook's GIT_INDEX_FILE etc., made absolute by the shim
        self.root = Path(root).expanduser().resolve()
        if not plugins.is_consolidated(self.root):
            raise ValueError(f"{self.root}: not a {plugins.NF_DIRNAME} root")
        self.top = Path(self.git("rev-parse", "--show-toplevel", cwd=self.root).strip())
        rel = self.root.relative_to(self.top)
        self.prefix = "" if rel == Path(".") else rel.as_posix()

    # ---- git -------------------------------------------------------------------

    def git(self, *args, cwd=None, check=True, data=None, text=True):
        r = subprocess.run(["git", *args], cwd=cwd or self.top, env=self._env, input=data,
                           capture_output=True, text=text)
        if check and r.returncode:
            err = r.stderr if text else r.stderr.decode(errors="replace")
            raise RuntimeError(f"git {' '.join(args)}: {err.strip()}")
        return r.stdout

    def _path(self, rel) -> str:
        return f"{self.prefix}/{rel}" if self.prefix else str(rel)

    def show(self, rel) -> str:
        """`rel` as the author sees it: relative to the repository toplevel."""
        return self._path(Path(rel).as_posix())

    def rev(self, ref) -> str | None:
        out = self.git("rev-parse", "-q", "--verify", f"{ref}^{{commit}}", check=False).strip()
        return out or None

    def blob(self, treeish, rel) -> bytes | None:
        r = subprocess.run(["git", "cat-file", "blob", f"{treeish}:{self._path(rel)}"], cwd=self.top,
                           env=self._env, capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def doc_at(self, treeish, rel) -> dict | None:
        data = self.blob(treeish, rel)
        return None if data is None else json.loads(data)

    def changed(self, base, new) -> list[tuple[str, Path]]:
        """`(status, root-relative path)` for every file that differs, renames split."""
        out = self.git("diff-tree", "-r", "--no-renames", "--name-status", base, new, "--", self.prefix or ".")
        rows = []
        for line in out.splitlines():
            status, path = line.split("\t", 1)
            rows.append((status, Path(path).relative_to(self.prefix) if self.prefix else Path(path)))
        return rows

    @property
    def token(self) -> str:
        """The root's namespace token, from the declaration in the worktree (HEAD's, failing that)."""
        path = self.root / nfx.NAMESPACE_FILENAME
        doc = json.loads(path.read_text()) if path.is_file() else self.doc_at("HEAD", nfx.NAMESPACE_FILENAME)
        return (doc or {}).get("namespace") or ""

    def tag_of(self, series: tuple[str, str], version: str) -> str:
        """`tag_name` for a series of this root: its declaration's tag carries its token."""
        return tag_name(series, version, self.token if series == NAMESPACE_SERIES else "")

    def tags(self, merged=None) -> dict[tuple[str, str], set[str]]:
        """Released versions per series, from the repo's annotated or lightweight tags.
        Of the namespace tags only this root's own count - under `NAMESPACE_SERIES`;
        another root of the same repository keeps its own series."""
        args = ["for-each-ref", "refs/tags", "--format=%(refname:short)"]
        if merged:
            args += ["--merged", merged]
        token = self.token
        series: dict[tuple[str, str], set[str]] = {}
        for name in self.git(*args).split():
            parsed = parse_tag(name)
            if not parsed:
                continue
            key, version = parsed
            if key[0] == "namespace":
                if key[1] != token:
                    continue
                key = NAMESPACE_SERIES
            series.setdefault(key, set()).add(version)
        return series

    def extract(self, tree, dst: Path) -> None:
        """Write the root's subtree of `tree` into `dst`."""
        data = self.git("archive", "--format=tar", f"{tree}:{self.prefix}", text=False)
        dst.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dst, filter="data")

    # ---- the verdict -------------------------------------------------------------

    def check(self, rev=None, others=()) -> Verdict:
        """The pre-commit verdict on the index against HEAD, or - `rev` given -
        on that commit against its parent, with only the tags its parent saw."""
        if rev is None:
            new = self.git("write-tree").strip()
            base = self.rev("HEAD") or EMPTY_TREE
            tags = self.tags()
        else:
            sha = self.rev(rev)
            if sha is None:
                raise ValueError(f"{rev}: no such commit")
            new = f"{sha}^{{tree}}"
            parent = self.rev(f"{sha}^")
            base = parent or EMPTY_TREE
            tags = self.tags(merged=parent) if parent else {}
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / plugins.NF_DIRNAME
            self.extract(new, staged)
            others = self._others(others, staged)
            return self._verdict(staged, base, self.changed(base, new), tags, others)

    def _others(self, roots, own) -> list[Path]:
        """`roots` without this root - by path, and by namespace nid: another
        checkout of the same namespace (a clone, a worktree) is this root, and
        `own` stands in for it."""
        ns = Path(own) / nfx.NAMESPACE_FILENAME
        nid = nfx.read(ns).nid if ns.is_file() else None
        kept = []
        for r in (Path(r).resolve() for r in roots):
            other = r / nfx.NAMESPACE_FILENAME
            if r == self.root or (nid and other.is_file() and nfx.read(other).nid == nid):
                continue
            kept.append(r)
        return kept

    def _verdict(self, staged, base, changed, tags, others) -> Verdict:
        staged = staged.resolve()

        try:
            idx = NfxIndex(*others, staged)
        except exceptions.NfxViolation as e:
            return Verdict([str(e).replace(str(staged), str(self.root))], [], [])
        by_nid = {e.nid: e for e in idx.entries()}
        local = {nid: e for nid, e in by_nid.items() if e.registry_root == staged}
        docs = {nid: nfx.read(e.path) for nid, e in local.items()}
        rel_of = {nid: e.path.relative_to(staged) for nid, e in local.items()}
        nid_at = {rel: nid for nid, rel in rel_of.items()}
        stem_of = {e.path.stem.lower(): nid for nid, e in local.items()}

        touched: set[Path] = set()
        for status, rel in changed:
            if status == "D":
                continue
            if rel.suffix == ".nfx":
                touched.add(rel)
            elif rel.parts[0] == plugins._VALIDATORS_DIR and rel.suffix == ".py" and rel.stem.lower() in stem_of:
                touched.add(rel_of[stem_of[rel.stem.lower()]])

        issues: list[str] = []
        released: list[str] = []

        # every pin inside the root holds - the re-pin closure is in this commit
        for nid, doc in docs.items():
            for dep, pin in doc.dependencies:
                if dep in local and docs[dep].version != pin and rel_of[nid] not in touched:
                    issues.append(f"{self.show(rel_of[nid])}: pins {rel_of[dep].stem}@{pin}, it is now "
                                  f"{docs[dep].version} - re-pin it in this commit")
                elif dep not in by_nid and not any(ns.nid == dep for ns in idx.namespaces()):
                    issues.append(f"{self.show(rel_of[nid])}: pins {dep}@{pin}, which no root declares")

        # in-root dependants of what changed are re-validated
        dependants: dict[str, set[str]] = {}
        for nid, doc in docs.items():
            for dep, _ in doc.dependencies:
                dependants.setdefault(dep, set()).add(nid)
        todo = [nid_at[r] for r in touched if r in nid_at]
        full = set(todo)
        while todo:
            for d in dependants.get(todo.pop(), ()):
                if d not in full:
                    full.add(d)
                    todo.append(d)

        for nid in sorted(full, key=lambda n: str(rel_of[n])):
            rel, path, doc = rel_of[nid], local[nid].path, docs[nid]
            where = self.show(rel)
            issues += [f"{where}: {f}" for f in document_failures(idx, path)]
            issues += [f"{where}:{line}: labels array must be on one line" for line in _labels_split(path.read_text())]
            if rel in touched:
                issues += [f"{where}: {e}" for e in idx.check_dependency_versions(path)]
                if not doc.is_namespace and doc.name != rel.stem:
                    issues.append(f"{where}: name {doc.name!r} must be its stem {rel.stem!r}")
            for dep, _ in doc.dependencies:
                if doc.type == "ontology" and dep in by_nid and by_nid[dep].type == "knowledge":
                    issues.append(f"{where}: an ontology may not pin knowledge ({by_nid[dep].path.stem})")
            vpath = plugins.validators_path_for(path, [staged])
            if vpath is not None and vpath.is_file():
                digest = hashlib.sha256(vpath.read_bytes()).hexdigest()
                if doc.hash != digest:
                    issues.append(f"{where}: hash {doc.hash or '(missing)'} is not sha256(validators/{vpath.name}) "
                                  f"{digest[:12]}… - run `ontology.rehash` (`git config nf.runner` names the wrapper)")
            elif doc.hash:
                issues.append(f"{where}: carries a hash but validators/{path.stem}.py does not exist")

        ns_rel = Path(nfx.NAMESPACE_FILENAME)
        ns_path = staged / ns_rel
        if ns_rel in touched and ns_path.is_file():
            issues += [f"{self.show(ns_rel)}: {f}" for f in namespace_failures(idx, ns_path)]

        # versions: every committed change to a document is a release - the next
        # version after its latest tag, nothing else.
        # Its test file is not part of the document and may change alone.
        # A root that declares `"released": false` (test fixtures) is exempt from
        # this rule alone: its documents are still held to everything above.
        for rel in sorted(touched) if _is_released(staged) else ():
            series = series_of(rel)
            path = staged / rel
            if series is None or not path.is_file():
                continue
            where = self.show(rel)
            doc = json.loads(path.read_text())
            version = doc.get("version", "")
            if version_key(version) is None:
                issues.append(f"{where}: version {version!r} is not <major>.<minor>")
                continue
            seen = tags.get(series, set())
            latest = max(seen, key=version_key) if seen else None
            if latest is None or version == latest:
                if version not in seen:
                    released.append(self.tag_of(series, version))
                else:
                    tagged = self._doc_by_nid(self.tag_of(series, version), rel, doc.get("nid"))
                    if tagged is not None and tagged != doc:
                        issues.append(f"{where}: changed since {self.tag_of(series, version)} but still version "
                                      f"{version} - every change is a release: `nfx.release {rel.stem or 'namespace'}` "
                                      f"(the next is {' or '.join(sorted(next_versions(latest)))})")
                continue
            if version in seen:
                issues.append(f"{where}: version {version} is already released ({self.tag_of(series, version)}) - "
                              f"the next is {' or '.join(sorted(next_versions(latest)))}")
            elif version not in next_versions(latest):
                issues.append(f"{where}: version {version} skips past the latest release {latest} - "
                              f"expected {' or '.join(sorted(next_versions(latest)))}")
            else:
                released.append(self.tag_of(series, version))

        return Verdict(issues, sorted(self.show(rel_of[n]) for n in full), released)

    # ---- post-commit ---------------------------------------------------------------

    def tag(self) -> list[str]:
        """Annotate HEAD with one tag per document of the root it changed whose
        version has no tag yet. Idempotent; returns the tags made. A root that
        declares `"released": false` gets none."""
        head = self.rev("HEAD")
        if (self.doc_at(head, nfx.NAMESPACE_FILENAME) or {}).get("released") is False:
            return []
        base = self.rev("HEAD^") or EMPTY_TREE
        subject = self.git("log", "-1", "--format=%s", head).strip()
        existing = set(self.git("tag", "-l").split())
        changed = [(rel, series_of(rel)) for status, rel in self.changed(base, head) if status != "D"]
        docs = {rel: self.doc_at(head, rel) for rel, series in changed if series}
        stem_of = {d.get("nid"): rel.stem for rel, d in docs.items()}
        made = []
        for rel, series in changed:
            if series is None:
                continue
            doc = docs[rel]
            name = self.tag_of(series, doc.get("version", ""))
            if name in existing:
                continue
            before = self.doc_at(base, rel)
            if is_repin(before, doc):
                pins = ", ".join(f"{stem_of.get(n, n[:8])}@{v}" for n, v in _pins(doc).items()
                                 if _pins(before).get(n) != v)
                note = f"re-pin {pins} · {subject}"
            else:
                note = subject
                if isinstance(nf_events.parse(subject), nf_events.Arrival):
                    for line in self.git("log", "-1", "--format=%b", head).splitlines():
                        event = nf_events.parse(line.split(" · ", 1)[0])
                        if isinstance(event, nf_events.Arrival) and Path(event.path) == rel:
                            note = line
                            break
            self.git("tag", "-a", name, "-m", f"{name} — {note}", head)
            existing.add(name)
            made.append(name)
        return made

    # ---- release ---------------------------------------------------------

    def plan_release(self, targets, major=False, others=()) -> list["Step"]:
        """What releasing `targets` (stems, names or nids of this root) writes:
        each target at the next version after its latest tag, then every
        in-root dependant, deps first, re-pinned and bumped to its own next
        minor. Reads the worktree; writes nothing."""
        idx = NfxIndex(*self._others(others, self.root), self.root)
        local = {e.nid: e for e in idx.entries() if e.registry_root == self.root}
        docs = {nid: nfx.read(e.path) for nid, e in local.items()}
        rel_of = {nid: e.path.relative_to(self.root) for nid, e in local.items()}
        tags = self.tags()

        def find(key):
            k = key.lower()
            for nid, e in local.items():
                if k in (nid, e.path.stem.lower(), (docs[nid].name or "").lower()):
                    return nid
            raise ValueError(f"{key}: no such document in {self.root}")

        def latest(nid):
            seen = tags.get(series_of(rel_of[nid]), set())
            return max(seen, key=version_key) if seen else None

        seeds = [find(t) for t in targets]
        new: dict[str, str] = {}
        for nid in seeds:
            doc, last = docs[nid], latest(nid)
            if last is None:
                new[nid] = doc.version
                continue
            major_, minor = version_key(last)
            want = f"{major_ + 1}.0" if major else f"{major_}.{minor + 1}"
            if doc.version not in (last, want):
                raise ValueError(f"{rel_of[nid]}: version {doc.version} is neither the released {last} nor "
                                 f"the next {want} - leave `version` alone, release writes it")
            tagged = self.doc_at(self.tag_of(series_of(rel_of[nid]), last), rel_of[nid])
            current = {**json.loads(local[nid].path.read_text()), "version": last}
            if self._digest(rel_of[nid]):
                current["hash"] = self._digest(rel_of[nid])  # an edited validator is a change of the module
            if tagged == current:
                raise ValueError(f"{rel_of[nid]}: unchanged since {self.tag_of(series_of(rel_of[nid]), last)} - "
                                 f"nothing to release")
            new[nid] = want

        dependants: dict[str, set[str]] = {}
        for nid, doc in docs.items():
            for dep, _ in doc.dependencies:
                dependants.setdefault(dep, set()).add(nid)
        closure, todo = set(seeds), list(seeds)
        while todo:
            for d in dependants.get(todo.pop(), ()):
                if d not in closure:
                    closure.add(d)
                    todo.append(d)

        order: list[str] = []
        done: set[str] = set()

        def visit(nid):
            if nid in done:
                return
            done.add(nid)
            for dep, _ in docs[nid].dependencies:
                if dep in closure:
                    visit(dep)
            order.append(nid)

        for nid in sorted(closure, key=lambda n: str(rel_of[n])):
            visit(nid)

        steps = []
        for nid in order:
            doc, last = docs[nid], latest(nid)
            pins = tuple((d, new.get(d, v)) for d, v in doc.dependencies)
            repins = [f"{rel_of[d].stem}@{new[d]}" for d, v in doc.dependencies if d in new and new[d] != v]
            if nid not in new:
                new[nid] = doc.version if last is None else f"{version_key(last)[0]}.{version_key(last)[1] + 1}"
            carries = False
            if nid not in seeds and last is not None:
                tagged = self.doc_at(self.tag_of(series_of(rel_of[nid]), last), rel_of[nid])
                after = {**json.loads(local[nid].path.read_text()), "version": last}
                after.pop("dependencies", None)
                if tagged is not None:
                    tagged = {k: v for k, v in tagged.items() if k != "dependencies"}
                    carries = tagged != after
            steps.append(Step(rel_of[nid], doc.name or rel_of[nid].stem, doc.type, doc.version, new[nid],
                              repins, nid in seeds, carries,
                              nfx.dumps(dataclasses.replace(doc, version=new[nid], dependencies=pins,
                                                            hash=self._digest(rel_of[nid]) or doc.hash))))
        return steps

    def _digest(self, rel) -> str | None:
        """sha256 of a module's validators file in the worktree - what its
        `hash` must be; None when it has no validators."""
        v = plugins.validators_path_for(self.root / rel, [self.root])
        return hashlib.sha256(v.read_bytes()).hexdigest() if v is not None and v.is_file() else None

    def _companions(self, rels) -> list[str]:
        """The validators and test files of these modules that differ from HEAD:
        they travel in the module's release commit."""
        out = []
        for rel in rels:
            if len(rel.parts) != 2:
                continue  # the namespace declaration has none
            for p in _module_paths(rel.parts[0], rel.stem)[1:]:
                if self.git("status", "--porcelain", "--untracked-files=all", "--", self._path(p)).strip():
                    out.append(self._path(p))
        return out

    def release(self, targets, major=False, others=(), message=None,
                gate=None) -> tuple[str, list["Step"], list[str]]:
        """Write, validate, commit and tag the release `plan_release` computes -
        one commit, one annotated tag per document. An edited validators or
        test file of a released module goes into the same commit, and `hash`
        is rewritten to match the validators. Refuses an index holding
        anything else; on a refused verdict the worktree and index are put back.

        `gate(paths) -> issues` is asked once the documents are written and
        the git verdict holds, before the commit: what git cannot judge - the
        schema and the values, tested in a base. Any issue refuses."""
        steps = self.plan_release(targets, major, others)
        paths = [self._path(s.rel.as_posix()) for s in steps] + self._companions([s.rel for s in steps])
        staged = set(self.git("diff", "--cached", "--name-only").split())
        foreign = sorted(staged - set(paths))
        if foreign:
            raise ValueError(f"the index already holds {', '.join(foreign)} - commit or unstage it first")
        saved = {s.rel: (self.root / s.rel).read_text() for s in steps}
        for s in steps:
            (self.root / s.rel).write_text(s.text)
        self.git("add", "--", *paths)
        verdict = self.check(others=others)
        if verdict.issues:
            self._restore(saved, paths)
            raise ReleaseRefused(verdict.issues)
        if gate is not None:
            try:
                failed = gate([self.root / s.rel for s in steps])
            except BaseException:
                self._restore(saved, paths)
                raise
            if failed:
                self._restore(saved, paths)
                raise ReleaseRefused(failed)
        seeds = [s for s in steps if s.seed]
        subject = message or release_subject(seeds)
        body = [s.line() for s in steps if not s.seed]
        r = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=self.top, env=self._env, text=True,
                           input="\n\n".join([subject, "\n".join(body)]) if body else subject, capture_output=True)
        if r.returncode:
            self._restore(saved, paths)
            raise ReleaseRefused([line for line in (r.stdout + r.stderr).splitlines() if line.strip()])
        self.tag()  # a no-op when the post-commit hook already ran
        head = self.rev("HEAD")
        return head, steps, sorted(self.git("tag", "--points-at", head).split())

    def _restore(self, saved, paths):
        self.git("reset", "-q", "--", *paths)
        for rel, text in saved.items():
            (self.root / rel).write_text(text)

    # ---- rename ---------------------------------------------------------------

    def plan_rename(self, target, new) -> "RenamePlan":
        """What renaming `target` (stem, name or nid) to the stem `new` writes.
        Reads HEAD and the tags; writes nothing."""
        head = self.rev("HEAD")
        if head is None:
            raise ValueError("nothing committed yet")
        rel = self._find(target, head)
        kind, old = rel.parts[0], rel.stem
        if not nf_events.is_stem(new):
            raise ValueError(f"{new!r} is not a stem - lowercase kebab")
        if new == old:
            raise ValueError(f"{self.show(rel)} is already {new!r}")
        files = [(rel, Path(kind) / f"{new}.nfx")]
        for d, name in ((plugins._VALIDATORS_DIR, "{}.py"), ("tests", "test_{}.py")):
            if self.blob(head, Path(d) / name.format(old)) is not None:
                files.append((Path(d) / name.format(old), Path(d) / name.format(new)))
        taken = [b for _, b in files if self.blob(head, b) is not None or (self.root / b).exists()]
        if taken:
            raise ValueError(f"{new!r} is taken: {', '.join(self.show(b) for b in taken)}")
        if (kind, new) in self.tags():
            raise ValueError(f"{new!r} is reserved: tags {kind}/{new}/… exist")
        dirty = self.git("status", "--porcelain", "--", *(self._path(a.as_posix()) for a, _ in files))
        if dirty.strip():
            raise ValueError(f"{self.show(rel)} has uncommitted changes - commit or drop them first")
        tags = [(tag_name((kind, old), v), tag_name((kind, new), v))
                for v in sorted(self.tags().get((kind, old), ()), key=version_key)]
        return RenamePlan(kind, old, new, self.doc_at(head, rel)["nid"], files, tags)

    def _doc_by_nid(self, rev, rel, nid) -> dict | None:
        """The module `nid` at `rev`: at `rel`, else wherever its kind dir held it (before a rename)."""
        doc = self.doc_at(rev, rel)
        if doc is not None and doc.get("nid") == nid:
            return doc
        try:
            found = self._find(nid, rev)
        except ValueError:
            return None
        return self.doc_at(rev, found)

    def _find(self, key, rev) -> Path:
        k = str(key).lower()
        out = self.git("ls-tree", "-r", "--name-only", rev, "--", *(self._path(d) for d in plugins._KIND_SUBDIRS))
        for path in out.split():
            rel = Path(path).relative_to(self.prefix) if self.prefix else Path(path)
            if series_of(rel) is None:
                continue
            doc = self.doc_at(rev, rel) or {}
            if k in (rel.stem, doc.get("nid"), str(doc.get("name", "")).lower()):
                return rel
        raise ValueError(f"{key}: no such module in {self.root}")

    def rename(self, target, new, others=()) -> tuple[str, "RenamePlan"]:
        """Rename one module inside this root in one commit: its files
        moved, `name` and the test's validators path rewritten, its tags re-made
        under the new stem on the same commits and the old ones deleted. A
        rename changes the document, so it is a release like any other change
       : the module takes its next version and its in-root
        dependants are re-pinned and bumped in the same commit. Refuses an
        index holding anything; a refused verdict puts worktree, index and
        tags back."""
        plan = self.plan_rename(target, new)
        if self.git("diff", "--cached", "--name-only").strip():
            raise ValueError("the index is not empty - commit or unstage it first")
        old_paths = [self._path(a.as_posix()) for a, _ in plan.files]
        new_paths = [self._path(b.as_posix()) for _, b in plan.files]
        made: list[str] = []
        saved: dict[Path, str] = {}  # the dependants the release rewrites

        def undo():
            for t in made:
                self.git("tag", "-d", t, check=False)
            if saved:
                self._restore(saved, [self._path(r.as_posix()) for r in saved])
            self.git("reset", "-q", "--", *old_paths, *new_paths, check=False)
            for b in new_paths:
                (self.top / b).unlink(missing_ok=True)
            self.git("checkout", "HEAD", "--", *old_paths, check=False)

        try:
            for a, b in zip(old_paths, new_paths):
                (self.top / b).parent.mkdir(parents=True, exist_ok=True)
                self.git("mv", a, b)
            nfx_path = self.top / new_paths[0]
            nfx_path.write_bytes(nf_import.rename_to_stem(nfx_path.read_bytes(), plan.new)[0])
            for (_, b), path in zip(plan.files, new_paths):
                if b.parts[0] == "tests":
                    (self.top / path).write_text(rename_test(Path(self.top / path).read_text(), plan.old, plan.new))
            self.git("add", "--", *new_paths)
            for old_tag, new_tag in plan.tags:
                self._copy_tag(old_tag, new_tag, f"renamed from {old_tag}")
                made.append(new_tag)
            # released before: the rename is its next version, with the re-pin closure.
            # Never released: the commit is its first release, at the version it has.
            steps = self.plan_release([plan.nid], others=others) if plan.tags else []
            for s in steps:
                if s.rel != plan.files[0][1]:
                    saved[s.rel] = (self.root / s.rel).read_text()
                (self.root / s.rel).write_text(s.text)
            if steps:
                self.git("add", "--", *(self._path(s.rel.as_posix()) for s in steps))
            verdict = self.check(others=others)
            if verdict.issues:
                raise ReleaseRefused(verdict.issues)
            body = [s.line() for s in steps if not s.seed]
            self._commit("\n\n".join([plan.event.subject, "\n".join(body)]) if body else plan.event.subject)
        except Exception:
            undo()
            raise
        self.tag()  # a no-op when the post-commit hook already ran
        for old_tag, _ in plan.tags:
            self.git("tag", "-d", old_tag)
        return self.rev("HEAD"), plan

    def _commit(self, message) -> str:
        """Commit the index (hooks and all); ReleaseRefused with git's output on failure."""
        r = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=self.top, env=self._env, text=True,
                           input=message, capture_output=True)
        if r.returncode:
            raise ReleaseRefused([line for line in (r.stdout + r.stderr).splitlines() if line.strip()])
        return self.rev("HEAD")

    def _copy_tag(self, old, new, note):
        """`new` on `old`'s commit; an annotated one keeps its tagger and date,
        its message gets `note` appended."""
        fmt = "%(objecttype)%00%(*objectname)%00%(taggername)%00%(taggeremail)%00%(taggerdate:iso-strict)%00%(contents)"
        kind, commit, name, email, date, body = self.git(
            "for-each-ref", f"refs/tags/{old}", f"--format={fmt}").rstrip("\n").split("\0", 5)
        if kind != "tag":
            self.git("tag", new, f"{old}^{{commit}}")
            return
        _, sep, rest = body.strip().partition(" — ")
        message = f"{new} — {rest if sep else body.strip()} · {note}"
        env = {**self._env, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email.strip("<>"),
               "GIT_COMMITTER_DATE": date}
        r = subprocess.run(["git", "tag", "-a", new, commit, "-m", message], cwd=self.top, env=env,
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"git tag {new}: {r.stderr.strip()}")

    # ---- commit order ----------------------------------------------------------------

    def uncommitted(self) -> list[Path]:
        """Root-relative documents that differ from HEAD (staged, unstaged or new)."""
        out = self.git("status", "--porcelain", "--untracked-files=all", "--", self.prefix or ".")
        rels = []
        for line in out.splitlines():
            path = Path(line[3:].split(" -> ", 1)[-1].strip())
            rel = path.relative_to(self.prefix) if self.prefix else path
            if series_of(rel) and (self.root / rel).is_file():
                rels.append(rel)
        return rels

    def order(self, others=()) -> list[tuple[Path, str, str]]:
        """`uncommitted()` in dependency order - a diagnostic: one commit may hold them all."""
        rels = self.uncommitted()
        idx = NfxIndex(*self._others(others, self.root), self.root)
        by_nid = {nfx.read(self.root / r).nid: r for r in rels}

        def resolve(nid):
            p = idx.resolve(nid)
            return nfx.read(p) if p else None

        synth = nfx.Nfx(dependencies=tuple((nid, "") for nid in by_nid))
        tree = nfx.NfxTree(synth, resolve, extra_deps=idx.extra_deps)
        rows = []
        for nid in tree.topo_order():
            if nid in by_nid:
                doc = nfx.read(self.root / by_nid[nid])
                rows.append((by_nid[nid], doc.name, doc.version))
        if (self.root / nfx.NAMESPACE_FILENAME).is_file() and Path(nfx.NAMESPACE_FILENAME) in rels:
            ns = nfx.read(self.root / nfx.NAMESPACE_FILENAME)
            rows.insert(0, (Path(nfx.NAMESPACE_FILENAME), ns.name, ns.version))
        return rows

    # ---- install -------------------------------------------------------------------

    def hooks_dir(self) -> Path:
        """Where git, or the global chain, will run this repo's hooks from.

        With a `core.hooksPath` in effect (a global hooks directory,
        such as `~/.config/git/hooks`) git never reads the repo's own hooks dir; the
        global hook re-invokes `$(git rev-parse --git-dir)/hooks/<name>`. A local
        `core.hooksPath` would cut that producer off, so it is never set here."""
        if self.git("config", "--get", "core.hooksPath", check=False).strip():
            return Path(self.git("rev-parse", "--absolute-git-dir").strip()) / "hooks"
        return Path(self.git("rev-parse", "--git-path", "hooks").strip()).resolve()

    def shim(self, hook) -> str:
        task = {"pre-commit": "tree.check", "post-commit": "tree.tag"}[hook]
        return (
            "#!/bin/sh\n"
            f"{_SENTINEL} - versioned with the root; the code is neuro's `{task}`.\n"
            "# The wrapper is per clone, `git config nf.runner <wrapper>`, and has no default:\n"
            "# a guess could run another line's code (a legacy runner during the parallel period).\n"
            'runner="$(git config nf.runner)" || { echo "nf hook: nf.runner is not set - run tree.hooks" >&2; exit 1; }\n'
            "# git hands a hook relative paths; the wrapper changes directory before Python starts.\n"
            f"for v in {' '.join(_GIT_PATH_VARS)}; do\n"
            '    eval "p=\\${$v:-}"\n'
            '    case "$p" in ""|/*) ;; *) export "$v=$PWD/$p" ;; esac\n'
            "done\n"
            'root="$(cd "$(dirname "$0")/.." && pwd)"\n'
            f'exec "$runner" {task} --tree "$root"\n'
        )

    def stub(self, hook) -> str:
        target = f"$(git rev-parse --show-toplevel)/{self._path(SHIM_DIR)}/{hook}"
        return f'#!/bin/sh\n{_SENTINEL} - installed by `tree.hooks`.\nexec "{target}" "$@"\n'

    def hooks_state(self) -> str:
        """`current` when every shim and stub is what `install` would write and
        the wrapper is named, `none` when no hook is there, else `stale` - a
        shim from before a task was renamed calls a task that no longer exists."""
        hooks, shims = self.hooks_dir(), self.root / SHIM_DIR
        files = [(path, body) for hook in HOOKS
                 for path, body in ((shims / hook, self.shim(hook)), (hooks / hook, self.stub(hook)))]
        if not any(path.exists() for path, _ in files):
            return "none"
        same = all(path.is_file() and path.read_text(errors="replace") == body for path, body in files)
        return "current" if same and self.git("config", "--get", "nf.runner", check=False).strip() else "stale"

    def install(self, runner) -> list[str]:
        """Write the versioned shims into `<root>/.githooks/`, a stub per hook
        into `hooks_dir()`, and `nf.runner`. Refuses to replace a hook it did
        not write. Returns what it wrote."""
        hooks = self.hooks_dir()
        for hook in HOOKS:
            current = hooks / hook
            if current.exists() and _SENTINEL not in current.read_text(errors="replace"):
                raise FileExistsError(f"{current} exists and is not an nf hook - chain it by hand or move it away")
        wrote = []
        shims = self.root / SHIM_DIR
        shims.mkdir(exist_ok=True)
        hooks.mkdir(parents=True, exist_ok=True)
        for hook in HOOKS:
            for path, body in ((shims / hook, self.shim(hook)), (hooks / hook, self.stub(hook))):
                if not path.exists() or path.read_text() != body:
                    path.write_text(body)
                    wrote.append(str(path))
                path.chmod(0o755)
        self.git("config", "nf.runner", runner)
        self.track_notes()
        return wrote

    def track_notes(self) -> list[str]:
        """Make every remote fetch the origin notes: git
        fetches no `refs/notes/*` unless told, and a clone without them shows
        carried commits as if they were made here. Returns the remotes it
        changed. A push still names the ref itself (`tree.split` prints it)."""
        refspec = f"+{NOTES_REF}:{NOTES_REF}"
        changed = []
        for remote in self.git("remote").split():
            key = f"remote.{remote}.fetch"
            if refspec not in self.git("config", "--get-all", key, check=False).splitlines():
                self.git("config", "--add", key, refspec)
                changed.append(remote)
        return changed


# ---- move between roots -------------------------------------------------------


@dataclasses.dataclass
class MoveItem:
    kind: str
    stem: str                       # in the source
    landed: str                     # in the target (== stem unless --as)
    nid: str
    version: str
    files: list[tuple[Path, Path]]  # source-relative → target-relative, the .nfx first
    released: str | None            # the source's latest tag, None if never released
    released_at: str | None         # its commit


@dataclasses.dataclass
class MovePlan:
    source: "Repo"
    target: "Repo"
    source_token: str
    target_token: str
    items: list[MoveItem]           # dependencies first
    seed: str                       # the nid asked for

    def _messages(self, line) -> str:
        """The seed's line as the subject, then one line per module in the body."""
        seed = next(i for i in self.items if i.nid == self.seed)
        return f"{line(seed).split(' · ')[0]}\n\n" + "\n".join(line(i) for i in self.items)

    @property
    def departure_message(self) -> str:
        if len(self.items) == 1:
            return self.departure(self.items[0]).subject
        return self._messages(lambda i: self.departure(i).subject)

    @property
    def arrival_message(self) -> str:
        return self._messages(lambda i: f"{self.arrival(i).subject} · {self.whence(i)}")

    def departure(self, item) -> nf_events.Departure:
        return nf_events.Departure(item.kind, item.stem, self.target_token)

    def arrival(self, item) -> nf_events.Arrival:
        return nf_events.Arrival(item.kind, item.stem, self.source_token,
                                 item.landed if item.landed != item.stem else "")

    def whence(self, item) -> str:
        word = self.source_token or nf_events.ROOT_WORD
        if item.released is None:
            return f"never released in {word}"
        return f"released in {word} as {item.released} at {item.released_at[:12]}"


def _rest(others, *repos) -> list[Path]:
    rest = list(others)
    for repo in repos:
        rest = repo._others(rest, repo.root)
    return rest


def plan_move(source: Repo, target: Repo, key, with_dependants=False, as_="", others=()) -> MovePlan:
    """What moving `key` (stem, name or nid) from `source` into `target` writes -
    with `with_dependants`, together with everything in the source that depends
    on it. Reads HEAD, the worktrees and the tags; writes nothing."""
    if source.root == target.root:
        raise ValueError("source and target are the same root")
    idx = NfxIndex(*_rest(others, source, target), target.root, source.root)
    ns_src, ns_dst = idx.namespace_of(source.root), idx.namespace_of(target.root)
    if ns_src is None or ns_dst is None:
        raise ValueError("both roots need a namespace.nfx")
    if ns_src.nid == ns_dst.nid:
        raise ValueError("source and target are checkouts of the same namespace")
    head = source.rev("HEAD")
    if head is None:
        raise ValueError(f"{source.root}: nothing committed yet")
    seed_rel = source._find(key, head)
    seed = source.doc_at(head, seed_rel)["nid"]
    local = {e.nid: e for e in idx.entries() if e.registry_root == source.root}
    by_nid = {e.nid: e for e in idx.entries()}
    docs = {nid: nfx.read(e.path) for nid, e in local.items()}
    rel_of = {nid: e.path.relative_to(source.root) for nid, e in local.items()}

    dependants: dict[str, set[str]] = {}
    for nid, doc in docs.items():
        for dep, _ in doc.dependencies:
            dependants.setdefault(dep, set()).add(nid)
    closure, todo = {seed}, [seed]
    while todo:
        for d in dependants.get(todo.pop(), ()):
            if d not in closure:
                closure.add(d)
                todo.append(d)
    if len(closure) > 1 and not with_dependants:
        names = ", ".join(sorted(str(rel_of[n]) for n in closure - {seed}))
        raise ValueError(f"{source.show(seed_rel)} cannot leave alone - in-root dependants: {names} "
                         f"(--with-dependants moves the set)")
    if as_ and not nf_events.is_stem(as_):
        raise ValueError(f"{as_!r} is not a stem - lowercase kebab")

    order: list[str] = []

    def visit(nid):
        if nid not in order:
            for dep, _ in docs[nid].dependencies:
                if dep in closure:
                    visit(dep)
            order.append(nid)

    for nid in sorted(closure, key=lambda n: str(rel_of[n])):
        visit(nid)

    src_tags, dst_tags = source.tags(), target.tags()
    issues, items = [], []
    for nid in order:
        rel = rel_of[nid]
        kind, stem = rel.parts[0], rel.stem
        landed = as_ if nid == seed and as_ else stem
        files = [(rel, Path(kind) / f"{landed}.nfx")]
        for d, name in ((plugins._VALIDATORS_DIR, "{}.py"), ("tests", "test_{}.py")):
            if source.blob(head, Path(d) / name.format(stem)) is not None:
                files.append((Path(d) / name.format(stem), Path(d) / name.format(landed)))
        if source.git("status", "--porcelain", "--", *(source._path(a.as_posix()) for a, _ in files)).strip():
            issues.append(f"{source.show(rel)}: uncommitted changes - commit or drop them first")
        for _, b in files:
            if (target.root / b).exists():
                issues.append(f"{target.show(b)} exists in the target{' - pass --as' if nid == seed else ''}")
        if (kind, landed) in dst_tags:
            back = target.doc_at(tag_name((kind, landed), max(dst_tags[(kind, landed)], key=version_key)),
                                 Path(kind) / f"{landed}.nfx")
            if (back or {}).get("nid") != nid:
                issues.append(f"{kind}/{landed} is reserved in the target by its tags"
                              f"{' - pass --as' if nid == seed else ''}")
        seen = src_tags.get((kind, stem), set())
        released = max(seen, key=version_key) if seen else None
        released_at = None
        if released:
            name = tag_name((kind, stem), released)
            released_at = source.rev(name)
            tagged = source._doc_by_nid(name, rel, nid)
            # history made before every change was a release can still hold such a module
            if tagged is None or tagged != source.doc_at(head, rel):
                issues.append(f"{source.show(rel)}: unreleased edits since {name} - `nfx.release` it first")
        items.append(MoveItem(kind, stem, landed, nid, docs[nid].version, files, released and name, released_at))

    namespaces = {ns.nid: ns for ns in idx.namespaces()}
    reach, todo = {ns_dst.nid}, [ns_dst.nid]
    while todo:
        ns = namespaces.get(todo.pop())
        for dep, _ in (ns.dependencies if ns else ()):
            if dep not in reach:
                reach.add(dep)
                todo.append(dep)
    for nid in order:
        for dep, _ in docs[nid].dependencies:
            entry = by_nid.get(dep)
            if dep in closure or entry is None or entry.namespace_nid in reach:
                continue
            ns = namespaces.get(entry.namespace_nid)
            pin = f"{(ns.token or nf_events.ROOT_WORD) if ns else '?'}@{ns.version if ns else '?'}"
            issues.append(f"{source.show(rel_of[nid])} pins {entry.path.stem}, whose namespace the target does "
                          f"not reach - add {pin} ({entry.namespace_nid}) to {target.show(nfx.NAMESPACE_FILENAME)}")
    if issues:
        raise ReleaseRefused(sorted(set(issues)))
    return MovePlan(source, target, ns_src.token, ns_dst.token, items, seed)


def move(source: Repo, target: Repo, key, with_dependants=False, as_="", others=()) -> tuple[MovePlan, str, str]:
    """Move a module (or a dependant set) into another root: one
    `MIGRATE: … →` commit removing it from the source, then one `MIGRATE: … ←`
    commit adding it to the target, each module tagged at its version there. A
    set moves in one commit at each end - the modules pin one another, so no
    order of single moves keeps both roots valid - with one event line per
    module in the body. History stays where it was; the source keeps its tags.
    A refusal anywhere puts both back. Returns the plan and the two commits."""
    plan = plan_move(source, target, key, with_dependants, as_, others)
    for repo in (source, target):
        if repo.git("diff", "--cached", "--name-only").strip():
            raise ValueError(f"{repo.root}: the index is not empty - commit or unstage it first")
    src_pre, dst_pre = source.rev("HEAD"), target.rev("HEAD")
    src_paths = [source._path(a.as_posix()) for i in plan.items for a, _ in i.files]
    dst_paths = [target._path(b.as_posix()) for i in plan.items for _, b in i.files]
    dst_tags_pre = set(target.git("tag", "-l").split())
    rest = _rest(others, source, target)
    try:
        source.git("rm", "-q", "--", *src_paths)
        verdict = source.check(others=[*rest, target.root])
        if verdict.issues:
            raise ReleaseRefused(verdict.issues)
        departed = source._commit(plan.departure_message)
        for item in plan.items:
            for a, b in item.files:
                data = source.blob(src_pre, a)
                if b.suffix == ".nfx" and item.landed != item.stem:
                    data = nf_import.rename_to_stem(data, item.landed)[0]
                elif b.parts[0] == "tests" and item.landed != item.stem:
                    data = rename_test(data.decode(), item.stem, item.landed).encode()
                path = target.root / b
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        target.git("add", "--", *dst_paths)
        verdict = target.check(others=[*rest, source.root])
        if verdict.issues:
            raise ReleaseRefused(verdict.issues)
        arrived = target._commit(plan.arrival_message)
        target.tag()  # a no-op when the post-commit hook already ran
    except Exception:
        for t in set(target.git("tag", "-l").split()) - dst_tags_pre:
            target.git("tag", "-d", t, check=False)
        if dst_pre:
            target.git("reset", "-q", "--soft", dst_pre, check=False)
        target.git("reset", "-q", "--", *dst_paths, check=False)
        for p in dst_paths:
            (target.top / p).unlink(missing_ok=True)
        source.git("reset", "-q", "--soft", src_pre, check=False)
        source.git("reset", "-q", "--", *src_paths, check=False)
        source.git("checkout", src_pre, "--", *src_paths, check=False)
        raise
    return plan, departed, arrived


# ---- the whole history -------------------------------------------------------


@dataclasses.dataclass
class LogEntry:
    root: Path
    token: str
    sha: str
    date: str
    subject: str
    path: str             # the module's .nfx path, root-relative, at that commit
    version: str          # at the commit (its parent's, for a removal)
    tags: list[str]
    repin: bool = False   # the commit only follows a dependency: version and pins moved, nothing of its own


def _module_paths(kind, stem) -> list[str]:
    return [f"{kind}/{stem}.nfx", f"{plugins._VALIDATORS_DIR}/{stem}.py", f"tests/test_{stem}.py"]


def module_log(repo: Repo, key, roots=()) -> tuple[list[LogEntry], str | None]:
    """Every commit of a module, newest first, across its renames and moves:
    the file log in its root, continued under the old stem at each
    `REFACTOR:` and in the source root at each `MIGRATE: … ←` (paired by nid).
    An entry is marked `repin` where the commit changed nothing of the module
    but its version and the versions of its pins - a dependency's release.
    `roots` are the other roots the chain may pass through, found by token.
    Returns the entries and a note when the chain leaves this machine."""
    head = repo.rev("HEAD")
    rel = repo._find(key, head)
    nid = repo.doc_at(head, rel)["nid"]
    by_token: dict[str, Repo] = {}
    for r in [repo.root, *roots]:
        ns = Path(r) / nfx.NAMESPACE_FILENAME
        if ns.is_file():
            token = nfx.read(ns).namespace or ""
            by_token.setdefault(token, repo if Path(r).resolve() == repo.root else Repo(r))

    def token_of(r: Repo) -> str:
        return next((t for t, x in by_token.items() if x.root == r.root), "?")

    entries, seen, note = [], set(), None
    cur, rev, kind, stem = repo, head, rel.parts[0], rel.stem
    names: dict[Path, set[str]] = {}  # every stem the module had in each root: a rename moved its tags to the newest
    while cur is not None:
        names.setdefault(cur.root, set()).add(stem)
        paths = [cur._path(p) for p in _module_paths(kind, stem)]
        out = cur.git("log", "--format=%H%x00%cs%x00%B%x1e", rev, "--", *paths)
        tags_at: dict[str, list[str]] = {}
        for line in cur.git("for-each-ref", "refs/tags", "--format=%(refname:short) %(*objectname)%(objectname)").splitlines():
            name, obj = line.split(" ", 1)
            parsed = parse_tag(name)
            if parsed and parsed[0][0] == kind:
                tags_at.setdefault(obj[:40], []).append(name)
        # a split brought history made in another root: every commit older than
        # its `MIGRATE: split ← <token>` was made there, and says so in the Root column
        order, splits = {}, []
        for n, line in enumerate(cur.git("log", "--format=%H%x00%cs%x00%s", rev).splitlines()):
            sha, date, subject = line.split("\0", 2)
            order[sha] = n
            event = nf_events.parse(subject)
            if isinstance(event, nf_events.SplitIn):
                splits.append((n, sha, date, subject, event.source))
        here: list[tuple[int, LogEntry]] = []
        nxt = None
        for record in out.split("\x1e"):
            sha, _, rest = record.strip("\n").partition("\0")
            if not sha or (cur.root, sha) in seen:
                continue
            seen.add((cur.root, sha))
            date, _, message = rest.partition("\0")
            events = nf_events.parse_all(message)
            path = f"{kind}/{stem}.nfx"
            after, before = cur.doc_at(sha, path), cur.doc_at(f"{sha}^", path)
            doc = after or before or {}
            # its validator and its test are the module too: a commit that touches them is a change of its own
            repin = is_repin(before, after) and all(
                cur.blob(sha, p) == cur.blob(f"{sha}^", p) for p in _module_paths(kind, stem)[1:])
            origin = max((s for s in splits if s[0] < order[sha]), default=None)
            here.append((order[sha], LogEntry(
                cur.root, origin[4] if origin else token_of(cur), sha, date, message.split("\n", 1)[0], path,
                doc.get("version", ""),
                sorted(t for t in tags_at.get(sha, []) if parse_tag(t)[0][1] in names[cur.root]), repin)))
            arrival = next((e for e in events if isinstance(e, nf_events.Arrival)
                            and e.kind == kind and e.landed == stem), None)
            rename = next((e for e in events if isinstance(e, nf_events.Rename)
                           and e.kind == kind and e.new == stem), None)
            if arrival:
                source = by_token.get(arrival.source)
                if source is None:
                    note = f"the chain continues in {arrival.source or nf_events.ROOT_WORD}, not among the roots here"
                    break
                dep = nf_events.departure_of(source.top, source.prefix, arrival, nid, token_of(cur))
                if dep is None:
                    note = f"no matching departure in {source.root}"
                    break
                nxt = (source, dep, kind, arrival.stem)
                break
            if rename:
                nxt = (cur, f"{sha}^", kind, rename.stem)
                break
        if here:
            oldest = max(n for n, _ in here)
            for n, sha, date, subject, _source in splits:
                if n < oldest and (cur.root, sha) not in seen:
                    seen.add((cur.root, sha))
                    here.append((n, LogEntry(cur.root, token_of(cur), sha, date, subject, f"{kind}/{stem}.nfx", "", [])))
        entries += [entry for _n, entry in sorted(here, key=lambda item: item[0])]
        cur, rev, kind, stem = nxt if nxt else (None, None, None, None)
    return entries, note


def namespace_log(repo: Repo) -> list[LogEntry]:
    """Every commit of a root's `namespace.nfx`, newest first. A namespace is
    not renamed or moved, so its history is the one file in the one root."""
    head = repo.rev("HEAD")
    if head is None:
        raise ValueError("nothing committed yet")
    path = nfx.NAMESPACE_FILENAME
    if repo.blob(head, Path(path)) is None:
        raise ValueError(f"{repo.root}: no {path}")
    token = (repo.doc_at(head, path) or {}).get("namespace", "")
    tags_at: dict[str, list[str]] = {}
    for line in repo.git("for-each-ref", "refs/tags", "--format=%(refname:short) %(*objectname)%(objectname)").splitlines():
        name, obj = line.split(" ", 1)
        parsed = parse_tag(name)
        if parsed and parsed[0] == ("namespace", token):
            tags_at.setdefault(obj[:40], []).append(name)
    entries = []
    for record in repo.git("log", "--format=%H%x00%cs%x00%s%x1e", head, "--", repo._path(path)).split("\x1e"):
        sha, _, rest = record.strip("\n").partition("\0")
        if not sha:
            continue
        date, _, subject = rest.partition("\0")
        doc = repo.doc_at(sha, path) or repo.doc_at(f"{sha}^", path) or {}
        entries.append(LogEntry(repo.root, token, sha, date, subject, path, doc.get("version", ""),
                                sorted(tags_at.get(sha, []))))
    return entries
