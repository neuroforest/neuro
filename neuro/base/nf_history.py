"""
Synthesize a `.nf` root's git history from a legacy plugins repo


The legacy hooks commit one file at a time, bottom-up: a change, then one
`UPDATE: dependency` re-pin commit per dependent. The `.nf` release shape
is one commit per release carrying every tag it produced. This
module regroups the legacy log into such *events* and replays them, each
event's last tree mapped through `nf_import.plan_import`, into a fresh repo.

Grouping (`group`), oldest first along the first-parent line:

- a commit is a **re-pin** by structure: every file it changes is an `.nfx`
  whose only differences are `version` and the versions of existing pins.
  Messages vary too much to trust;
- a re-pin joins the current event;
- an **opener** (any other commit) joins it too when a module it modifies
  (not adds) changes a pin to a version released inside the event and it lands within
  `CASCADE_WINDOW` of the event's previous member - a bottom-up multi-module
  release; otherwise it opens a new event;
- an event never writes one module twice: a commit that would starts a new
  event, so every tag still names a commit where its module is at that
  version.

Events are contiguous runs of the legacy log, so each synthesized commit is the
legacy tree after the event's last member. The `namespace.nfx` given is in
every commit - the root has always been that namespace. Lightweight legacy
tags `<name>/<version>` become annotated `<type>/<stem>/<version>` tags on the
event holding their commit, tagger and date taken from that commit. A module
version the legacy repo never tagged (the old hook did not tag knowledge
cascade bumps) is tagged on the event where it first appears, its message
saying it is synthesized.

Names: every module's `name` is its stem in every commit
(`plan_import` rewrites it), and the messages follow - a module's old name in
a commit message or tag message becomes its stem (`renames`, `rename_in`), so
no historical name survives. The namespace declaration is tagged
`namespace/<token>/<version>` on the first commit. An event whose mapped tree equals
the previous one and that carries no tag (a legacy commit that touched only
unmapped files) is dropped.

The early history predates the `type` field: a typeless module is placed by
the first type its nid later declares (`declared_types`), its bytes kept. A
tree holding one nid in two files (a move done as a copy) keeps the higher
version (`drop_duplicates`).

Problems in a historical tree (a hash that did not match then, a file the
mapping has no place for) are facts of history, not reasons to stop: they are
collected per event in the `Report`, and the tree is mapped without them. A
tree the index refuses outright (`NfxViolation`) keeps the previous event's
tree and is reported as fatal.
"""

import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from neuro.base import nf_import, nfx
from neuro.utils import exceptions

CASCADE_WINDOW = 600  # seconds


@dataclass
class Change:
    status: str
    path: str
    before: dict | None
    after: dict | None

    @property
    def is_nfx(self) -> bool:
        return self.path.endswith(".nfx")


@dataclass
class Commit:
    sha: str
    message: str
    author: str     # "Name <email> <epoch> <tz>", as fast-import takes it
    committer: str
    time: int
    changes: list[Change]

    @property
    def subject(self) -> str:
        return self.message.splitlines()[0] if self.message else ""


@dataclass
class Event:
    members: list[Commit] = field(default_factory=list)
    written: set[str] = field(default_factory=set)

    @property
    def opener(self) -> Commit:
        return self.members[0]

    @property
    def last(self) -> Commit:
        return self.members[-1]


@dataclass
class Report:
    events: int = 0
    commits: int = 0
    tags: int = 0
    legacy_tags: int = 0
    synthesized: int = 0
    empty: int = 0          # events dropped: same tree as the previous one, no tag
    renamed: int = 0        # messages whose module names were rewritten
    bumped: int = 0         # releases written for changes the legacy repo made without one
    head: dict = field(default_factory=dict)  # rel → content of the modules in the last commit
    warnings: list[str] = field(default_factory=list)
    fatal: list[str] = field(default_factory=list)
    unmapped_tags: list[str] = field(default_factory=list)


def _git(repo, *args, data: bytes | None = None) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], input=data,
                          capture_output=True, check=True).stdout.decode()


class _Cat:
    """One `git cat-file --batch` for every blob read."""

    def __init__(self, repo):
        self._p = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, spec: str) -> bytes | None:
        self._p.stdin.write((spec + "\n").encode())
        self._p.stdin.flush()
        header = self._p.stdout.readline().decode()
        if header.endswith("missing\n"):
            return None
        data = self._p.stdout.read(int(header.split()[2]))
        self._p.stdout.read(1)
        return data

    def json(self, spec: str) -> dict | None:
        raw = self.read(spec)
        if raw is None:
            return None
        try:
            doc = json.loads(raw)
        except ValueError:
            return None
        return doc if isinstance(doc, dict) else None

    def close(self):
        self._p.stdin.close()
        self._p.wait()


def _pins(doc: dict) -> dict[str, str]:
    out = {}
    for dep in doc.get("dependencies") or []:
        nid, _, version = str(dep).partition("@")
        out[nid] = version
    return out


def is_repin(before: dict | None, after: dict | None) -> bool:
    """Only `version` and the versions of existing pins changed."""
    if before is None or after is None:
        return False
    rest = lambda d: {k: v for k, v in d.items() if k not in ("version", "dependencies")}  # noqa: E731
    if rest(before) != rest(after):
        return False
    pb, pa = _pins(before), _pins(after)
    return pb.keys() == pa.keys() and pb != pa


def read_log(repo) -> list[Commit]:
    """The first-parent log, oldest first, with each commit's changes parsed."""
    cat = _Cat(repo)
    fmt = "%H%x00%an <%ae> %ad%x00%cn <%ce> %cd%x00%ct%x00%B%x01"
    raw = _git(repo, "log", "--reverse", "--first-parent", "--date=raw", f"--format={fmt}")
    commits = []
    parent = None
    for rec in raw.split("\x01"):
        rec = rec.lstrip("\n")
        if not rec:
            continue
        sha, author, committer, time, message = rec.split("\x00")
        changes = []
        args = ["diff-tree", "--no-commit-id", "-r", "-M", "--name-status", sha]
        if parent is None:
            args.insert(1, "--root")
        for line in _git(repo, *args).splitlines():
            status, *paths = line.split("\t")
            old, new = paths[0], paths[-1]
            nfx_file = new.endswith(".nfx") or old.endswith(".nfx")
            before = cat.json(f"{parent}:{old}") if nfx_file and parent and status[0] != "A" else None
            after = cat.json(f"{sha}:{new}") if nfx_file and status[0] != "D" else None
            changes.append(Change(status[0], new, before, after))
        commits.append(Commit(sha, message.strip(), author, committer, int(time), changes))
        parent = sha
    cat.close()
    return commits


def _commit_is_repin(c: Commit) -> bool:
    return bool(c.changes) and all(ch.is_nfx and ch.status == "M" and is_repin(ch.before, ch.after)
                                   for ch in c.changes)


def _written(c: Commit) -> set[str]:
    return {ch.after["nid"] for ch in c.changes if ch.after and ch.after.get("nid")}


def group(commits: list[Commit]) -> list[Event]:
    """Regroup the legacy log into release events (see the module docstring)."""
    events: list[Event] = []
    released: dict[tuple[str, str], int] = {}   # (nid, version) -> index of the event that wrote it
    for c in commits:
        ev = events[-1] if events else None
        written = _written(c)
        joins = False
        if ev is not None and not (written & ev.written):
            if _commit_is_repin(c):
                joins = True
            elif c.time - ev.last.time < CASCADE_WINDOW:
                here = len(events) - 1
                for ch in c.changes:
                    if ch.before and ch.after:
                        pb, pa = _pins(ch.before), _pins(ch.after)
                        if any(pb.get(n) != v and released.get((n, v)) == here for n, v in pa.items()):
                            joins = True
        if not joins:
            ev = Event()
            events.append(ev)
        ev.members.append(c)
        ev.written |= written
        for ch in c.changes:
            if ch.after and ch.after.get("nid") and ch.after.get("version"):
                released.setdefault((ch.after["nid"], str(ch.after["version"])), len(events) - 1)
    return events


def declared_types(commits: list[Commit]) -> dict[str, str]:
    """nid → the first `type` that nid ever declares. The early history
    predates the field; a typeless module is placed by what it later became,
    and as an ontology if it never says (`build`)."""
    out: dict[str, str] = {}
    for c in commits:
        for ch in c.changes:
            if ch.after and ch.after.get("nid") and ch.after.get("type"):
                out.setdefault(ch.after["nid"], ch.after["type"])
    return out


# Not in the plugins repo, but named in its messages.
_EXTRA_RENAMES = {"Metaontology": "metaontology"}


def renames(commits: list[Commit]) -> dict[str, str]:
    """Every module name the history ever declared that differs from the
    module's stem → that stem. Under the key `""`, the set of stems itself,
    for the module slot of a release subject (`rename_in`)."""
    out: dict = dict(_EXTRA_RENAMES)
    stems = set()
    for c in commits:
        for ch in c.changes:
            name = (ch.after or {}).get("name")
            stem = Path(ch.path).stem
            if ch.is_nfx:
                stems.add(stem)
                if isinstance(name, str) and name and name != stem:
                    out[name] = stem
    out[""] = stems
    return out


# `RELEASE: ontology Demo 3.0` - the module slot of a subject, whatever case the message used
_SUBJECT_SLOT = re.compile(r"^([A-Z]+: (?:ontology|knowledge|metaontology) )(\S+)", re.M)


def rename_in(text: str, table: dict) -> str:
    """`text` with each whole-word old module name replaced by its stem,
    longest names first (`Custom antimicrobial agents` before `Antimicrobial
    agents`). A name inside a longer word or hyphenated name is left alone.
    In the module slot of a subject line, a stem in another case (`Demo`) is
    lowercased too; elsewhere a word is only replaced when it was a name."""
    names = {k: v for k, v in table.items() if k}
    stems = {s.lower(): s for s in table.get("", ())}
    if names:
        pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                             + r")(?![\w-])")
        text = pattern.sub(lambda m: names[m[1]], text)
    return _SUBJECT_SLOT.sub(lambda m: m[1] + stems.get(m[2].lower(), m[2]), text)


def legacy_tags(repo) -> dict[str, list[str]]:
    """Commit sha → the tag names pointing at it (lightweight or annotated)."""
    out: dict[str, list[str]] = {}
    for line in _git(repo, "for-each-ref", "refs/tags",
                     "--format=%(refname:short)|%(*objectname)|%(objectname)").splitlines():
        name, peeled, obj = line.split("|")
        out.setdefault(peeled or obj, []).append(name)
    return out


def extract(repo, sha: str, into: Path) -> list[str]:
    """Write the tree of `sha` into `into` (emptied first); regular files only.
    Returns the paths skipped (symlinks - they would read outside the tree)."""
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha],
                         capture_output=True, check=True).stdout
    skipped = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                skipped.append(member.name)
                continue
            dst = into / member.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(tf.extractfile(member).read())
    return skipped


def _version_key(version) -> tuple:
    try:
        return tuple(int(p) for p in str(version).split("."))
    except ValueError:
        return ()


def drop_duplicates(tree: Path) -> list[str]:
    """Where one nid has two `.nfx` files in a historical tree - a move done as
    a copy, the stale file deleted a commit or two later - keep the higher
    version and delete the other. Returns what was dropped."""
    by_nid: dict[str, list[tuple[tuple, Path]]] = {}
    for path in tree.rglob("*.nfx"):
        try:
            doc = json.loads(path.read_bytes())
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("nid"):
            by_nid.setdefault(doc["nid"], []).append((_version_key(doc.get("version")), path))
    dropped = []
    for nid, files in by_nid.items():
        if len(files) < 2:
            continue
        files.sort(key=lambda f: (f[0], len(f[1].parts)))
        keep = files[-1][1]
        for _, path in files[:-1]:
            path.unlink()
            dropped.append(f"{path.relative_to(tree)} (duplicate nid {nid[:8]}, kept {keep.relative_to(tree)})")
    return dropped


def _data(payload: bytes) -> bytes:
    return b"data %d\n" % len(payload) + payload + b"\n"


@dataclass
class Releases:
    """What the replay has written so far, per module nid (the rule:
    every committed change to a module is a release)."""
    written: dict[str, str] = field(default_factory=dict)             # nid → version in the last commit
    legacy: dict[str, str] = field(default_factory=dict)              # nid → the legacy version it had then
    body: dict[str, dict] = field(default_factory=dict)               # nid → that document, `version` aside
    last_for: dict[tuple[str, str], str] = field(default_factory=dict)  # (nid, legacy version) → version written
    bumped: int = 0                                                   # releases the legacy repo never made


def _next_minor(version: str) -> str | None:
    key = _version_key(version)
    return f"{key[0]}.{key[1] + 1}" if len(key) == 2 else None


def release_changes(moves, state: Releases) -> dict[Path, bytes]:
    """The module files of one mapped tree as the replay writes them, so that
    no commit changes a module and leaves its version alone.

    The legacy hooks re-pinned a knowledge dependant without bumping it, and
    sometimes rewrote its content at the same version. Here a module whose
    document differs from the one last written takes the next minor version
    after it - or the legacy version, where the legacy repo released it and
    that is higher. A pin on a module whose versions were shifted this way is
    rewritten to the version written for it, which changes the dependant, so
    the bump cascades; dependencies are settled before their dependants.
    Bytes are edited in place - the `version` value and the pins - so the
    formatting of history stays as it was. Returns `rel → content` for the
    modules; `state` is advanced."""
    by_nid = {m.nid: m for m in moves if m.nid}
    docs = {nid: json.loads(m.content) for nid, m in by_nid.items()}
    # a module's validators are part of it (its test is not): their change is a change of the module
    validators = {m.rel.stem: hashlib.sha256(m.content).hexdigest() for m in moves
                  if not m.nid and m.rel.parts[0] == "validators"}
    out: dict[Path, bytes] = {}
    done: set[str] = set()

    def visit(nid):
        if nid in done:
            return
        done.add(nid)
        doc, content = docs[nid], by_nid[nid].content
        pins = _pins(doc)
        for dep in pins:
            if dep in docs:
                visit(dep)
        legacy = str(doc.get("version", ""))
        body = {k: v for k, v in doc.items() if k != "version"}
        body["\0validators"] = validators.get(by_nid[nid].rel.stem)
        if pins:
            body["dependencies"] = [f"{d}@{state.last_for.get((d, v), v)}" for d, v in pins.items()]
            for d, v in pins.items():
                w = state.last_for.get((d, v), v)
                if w != v:
                    content = content.replace(f'"{d}@{v}"'.encode(), f'"{d}@{w}"'.encode())
        before = state.written.get(nid)
        if before is None:
            version = legacy
        elif body == state.body[nid] and legacy == state.legacy[nid]:
            version = before
        elif _version_key(legacy) > _version_key(before) or _next_minor(before) is None:
            version = legacy
        else:
            version = _next_minor(before)
            state.bumped += 1
        if version != legacy:
            content = re.sub(rb'("version"\s*:\s*")' + re.escape(legacy.encode()) + rb'"',
                             rb"\g<1>" + version.encode() + b'"', content, count=1)
            if str(json.loads(content).get("version")) != version:
                raise RuntimeError(f"{by_nid[nid].rel}: could not write version {version} over {legacy}")
        state.written[nid], state.legacy[nid], state.body[nid] = version, legacy, body
        state.last_for[(nid, legacy)] = version
        out[by_nid[nid].rel] = content

    for nid in sorted(by_nid, key=lambda n: str(by_nid[n].rel)):
        visit(nid)
    return out


def _module_index(moves) -> dict[tuple[str, str], tuple[str, str]]:
    """(legacy tag name, version) → (type, stem) for the modules of one mapped tree.
    A legacy tag is named after the module's source `name` lowercased (the
    old hook) - the stem is accepted too."""
    out = {}
    for m in moves:
        if not m.nid:
            continue
        doc = json.loads(m.content)
        stem = m.rel.stem
        for key in {m.name.lower(), stem.lower()}:
            if key:
                out[(key, str(doc.get("version", "")))] = (m.rel.parent.name, stem)
    return out


def build(src, dst, namespace: nfx.Nfx, scratch, *, branch="master", progress=None) -> Report:
    """Replay `src`'s history into the new repo `dst` (must not exist).
    `scratch` is a directory for the per-event trees."""
    src, dst, scratch = Path(src), Path(dst), Path(scratch)
    if dst.exists() and any(dst.iterdir()):
        raise FileExistsError(f"{dst} exists and is not empty")
    report = Report()
    commits = read_log(src)
    events = group(commits)
    tags_at = legacy_tags(src)
    declared = declared_types(commits)
    type_of = lambda nid: declared.get(nid, "ontology")  # noqa: E731
    report.commits, report.events = len(commits), len(events)
    report.legacy_tags = sum(len(v) for v in tags_at.values())

    subprocess.run(["git", "init", "-q", "-b", branch, str(dst)], check=True)
    fi = subprocess.Popen(["git", "-C", str(dst), "fast-import", "--quiet", "--done"],
                          stdin=subprocess.PIPE)
    tree_dir = scratch / "plugins"
    moves = None
    previous: dict[Path, str] = {}
    legacy_keys = {(t.rpartition("/")[0].lower(), t.rpartition("/")[2]) for ts in tags_at.values() for t in ts}
    table = renames(commits)
    made: dict[str, str] = {}
    releases = Releases()
    mark = 0                      # the last commit written
    signature = None              # its tree
    for i, ev in enumerate(events, start=1):
        for path in extract(src, ev.last.sha, tree_dir):
            report.warnings.append(f"{ev.last.sha[:7]}: skipped non-file {path}")
        for path in drop_duplicates(tree_dir):
            report.warnings.append(f"{ev.last.sha[:7]}: dropped {path}")
        try:
            mapping = nf_import.plan_import(tree_dir, namespace, type_of=type_of)
            moves = mapping.moves
            report.warnings += [f"{ev.last.sha[:7]}: {i}" for i in mapping.issues]
        except exceptions.NfxViolation as err:
            report.fatal.append(f"{ev.last.sha[:7]}: {err} - previous tree kept")
            if moves is None:
                moves = []
        message = ev.opener.message
        extra = [c.subject for c in ev.members[1:] if not _commit_is_repin(c)]
        if extra:
            message += "\n\n" + "\n".join(extra)
        renamed = rename_in(message, table)
        subject_of = lambda c: rename_in(c.subject, table)  # noqa: E731

        # No commit changes a module and leaves its version alone
        contents = release_changes(moves, releases)
        nid_at = {(m.rel.parent.name, m.rel.stem): m.nid for m in moves if m.nid}

        # tags first: an event without a tree change is dropped only when it tags nothing
        tags: list[tuple[str, str, str]] = []   # (name, tagger, message)
        index = _module_index(moves)
        for c in ev.members:
            for legacy in tags_at.get(c.sha, []):
                name, _, version = legacy.rpartition("/")
                hit = index.get((name.lower(), version))
                if hit is None:
                    report.unmapped_tags.append(f"{legacy} at {c.sha[:7]}")
                    continue
                written = releases.last_for.get((nid_at[hit], version), version)
                new = f"{hit[0]}/{hit[1].lower()}/{written}"
                if new in made:
                    if written == version:
                        report.unmapped_tags.append(f"{legacy} → {new} already made from {made[new]}")
                    continue
                made[new] = legacy
                tags.append((new, c.committer, f"{new} — {subject_of(c)}"))
        # A version the legacy hook never tagged (knowledge cascade bumps)
        # is tagged where it first appears, and says so. So is a release the
        # legacy repo never made at all.
        current = {}
        for m in moves:
            if m.nid:
                legacy = str(json.loads(m.content).get("version", ""))
                version = releases.written[m.nid]
                current[m.rel] = version
                new = f"{m.rel.parent.name}/{m.rel.stem.lower()}/{version}"
                keys = {(m.rel.stem.lower(), version), (m.name.lower(), version)}
                if version and previous.get(m.rel) != version and new not in made \
                        and (version != legacy or not keys & legacy_keys):
                    made[new] = "(synthesized)"
                    report.synthesized += 1
                    why = "untagged in the legacy repo" if version == legacy else \
                        f"changed in the legacy repo at version {legacy} with no release"
                    tags.append((new, ev.last.committer, f"{new} — synthesized: {why}; {subject_of(ev.opener)}"))
        previous = current
        if mark == 0:
            new = nf_import.namespace_tag(namespace.namespace, namespace.version)
            made[new] = "(synthesized)"
            report.synthesized += 1
            tags.append((new, ev.last.committer,
                         f"{new} — synthesized: the root's declaration, in every commit; {subject_of(ev.opener)}"))

        tree = hashlib.sha256(b"".join(str(m.rel).encode() + b"\0" + contents.get(m.rel, m.content) + b"\0"
                                       for m in moves)).digest()
        if tree == signature and not tags:
            report.empty += 1
            if progress:
                progress(i, len(events))
            continue
        signature = tree
        mark += 1
        report.renamed += renamed != message
        out = [b"commit refs/heads/%s\n" % branch.encode(), b"mark :%d\n" % mark,
               b"author %s\n" % ev.opener.author.encode(),
               b"committer %s\n" % ev.last.committer.encode(),
               _data(renamed.encode() + b"\n")]
        if mark > 1:
            out.append(b"from :%d\n" % (mark - 1))
        out.append(b"deleteall\n")
        for m in moves:
            out.append(b"M 100644 inline %s\n" % str(m.rel).encode())
            out.append(_data(contents.get(m.rel, m.content)))
        for name, tagger, text in tags:
            out += [b"tag %s\n" % name.encode(), b"from :%d\n" % mark,
                    b"tagger %s\n" % tagger.encode(), _data(text.encode() + b"\n")]
        fi.stdin.write(b"".join(out))
        if progress:
            progress(i, len(events))
    fi.stdin.write(b"done\n")
    fi.stdin.close()
    if fi.wait() != 0:
        raise RuntimeError("git fast-import failed")
    _git(dst, "checkout", "-q", branch)
    report.tags = len(made)
    report.events = mark
    report.bumped = releases.bumped
    report.head = contents if events else {}
    return report


def check_tags(dst) -> list[str]:
    """Every `<type>/<stem>/<version>` tag names a commit where
    `<type>/<stem>.nfx` is at that version; `namespace/[<token>/]<version>`
    names one where `namespace.nfx` is. The token is the root's current one, not
    checked against the tagged commit: a renamed token takes its series along."""
    cat = _Cat(dst)
    issues = []
    for tag in _git(dst, "tag").split():
        parts = tag.split("/")
        if parts[0] == "namespace" and len(parts) in (2, 3):
            doc = cat.json(f"{tag}:{nfx.NAMESPACE_FILENAME}")
            if doc is None or str(doc.get("version")) != parts[-1]:
                issues.append(f"{tag}: {nfx.NAMESPACE_FILENAME} is not at {parts[-1]} there")
            continue
        kind, stem, version = parts
        doc = cat.json(f"{tag}:{kind}/{stem}.nfx")
        if doc is None:
            # the stem was lowercased for the tag; find the file case-insensitively
            names = _git(dst, "ls-tree", "--name-only", f"{tag}:{kind}").split()
            match = [n for n in names if n.lower() == f"{stem}.nfx"]
            doc = cat.json(f"{tag}:{kind}/{match[0]}") if match else None
        if doc is None:
            issues.append(f"{tag}: no {kind}/{stem}.nfx at the tagged commit")
        elif str(doc.get("version")) != version:
            issues.append(f"{tag}: file is at {doc.get('version')}")
    cat.close()
    return issues
