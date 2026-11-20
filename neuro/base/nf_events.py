"""
The commit subjects that record a module's rename or move.

History is never copied between `.nf` roots: each rename and each move is one
commit at each end, and its subject is the record. Three forms, one line each,
written only by `nf.rename` / `nf.move` and read by `nf.log`:

    REFACTOR: <kind> <old> → <new>                 a rename inside one root
    MIGRATE: <kind> <stem> → <token>               the source end of a move
    MIGRATE: <kind> <stem> ← <token>[ as <new>]    the target end of a move

`<kind>` is the subdir (`ontology`, `knowledge`), stems are lowercase kebab
(name = stem), and `<token>` names the other root, `root`
standing for the empty token. The two ends of a move are paired by the module's
nid in the trees either side of the commits, never by the subject alone.
"""

import dataclasses
import json
import re
import subprocess
from pathlib import PurePosixPath

from neuro.base import nfx, plugins

KINDS = plugins._KIND_SUBDIRS
ROOT_WORD = "root"
_STEM = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_KIND = "|".join(KINDS)
_RENAME = re.compile(rf"^REFACTOR: ({_KIND}) ({_STEM}) → ({_STEM})$")
_DEPART = re.compile(rf"^MIGRATE: ({_KIND}) ({_STEM}) → ({_STEM})$")
_ARRIVE = re.compile(rf"^MIGRATE: ({_KIND}) ({_STEM}) ← ({_STEM})(?: as ({_STEM}))?$")


def is_stem(stem: str) -> bool:
    return bool(re.fullmatch(_STEM, stem))


def _word(token: str) -> str:
    if not nfx.is_namespace_token(token) or token == ROOT_WORD:
        raise ValueError(f"not a namespace token: {token!r}")
    return token or ROOT_WORD


def _token(word: str) -> str:
    return "" if word == ROOT_WORD else word


@dataclasses.dataclass(frozen=True)
class Event:
    kind: str
    stem: str

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"not a module kind: {self.kind!r}")
        for stem in self._stems():
            if not is_stem(stem):
                raise ValueError(f"not a stem: {stem!r}")

    def _stems(self) -> tuple[str, ...]:
        return (self.stem,)

    @property
    def path(self) -> str:
        """The `.nfx` path, root-relative, the commit's tree holds (or held) the module at."""
        return f"{self.kind}/{self.stem}.nfx"


@dataclasses.dataclass(frozen=True)
class Rename(Event):
    """`stem` is the old name, `new` the one the module has after the commit."""
    new: str

    def _stems(self):
        return self.stem, self.new

    @property
    def subject(self) -> str:
        return f"REFACTOR: {self.kind} {self.stem} → {self.new}"


@dataclasses.dataclass(frozen=True)
class Departure(Event):
    """The source end: the module at `stem` left for the root `to`."""
    to: str

    def __post_init__(self):
        super().__post_init__()
        _word(self.to)

    @property
    def subject(self) -> str:
        return f"MIGRATE: {self.kind} {self.stem} → {_word(self.to)}"


@dataclasses.dataclass(frozen=True)
class Arrival(Event):
    """The target end: the module, `stem` in the root `source`, arrived as `new`
    (`stem` itself when the move did not rename it)."""
    source: str
    new: str = ""

    def __post_init__(self):
        super().__post_init__()
        _word(self.source)

    def _stems(self):
        return (self.stem, self.new) if self.new else (self.stem,)

    @property
    def landed(self) -> str:
        return self.new or self.stem

    @property
    def path(self) -> str:
        return f"{self.kind}/{self.landed}.nfx"

    @property
    def subject(self) -> str:
        tail = f" as {self.new}" if self.new and self.new != self.stem else ""
        return f"MIGRATE: {self.kind} {self.stem} ← {_word(self.source)}{tail}"


def parse(subject: str) -> Rename | Departure | Arrival | None:
    """The event a commit subject records, None for any other subject. Only the
    first line counts; anything not in the exact grammar is not an event."""
    line = subject.split("\n", 1)[0]
    if m := _RENAME.match(line):
        return Rename(m[1], m[2], m[3]) if m[2] != m[3] else None
    if m := _DEPART.match(line):
        return Departure(m[1], m[2], _token(m[3]))
    if m := _ARRIVE.match(line):
        new = m[4] if m[4] and m[4] != m[2] else ""
        return Arrival(m[1], m[2], _token(m[3]), new)
    return None


def parse_all(message: str) -> list[Rename | Departure | Arrival]:
    """Every event a commit message records: its subject's, then one per body
    line in the grammar (a set moves in one commit), a line's
    ` · <note>` tail aside. Repeats dropped, order kept."""
    events = []
    for line in message.split("\n"):
        event = parse(line.split(" · ", 1)[0].strip())
        if event is not None and event not in events:
            events.append(event)
    return events


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True)


def nid_at(repo, rev: str, path: str) -> str | None:
    """The nid of the `.nfx` at `rev:path` (repo-relative), None when the tree has no such file."""
    shown = _git(repo, "show", f"{rev}:{path}")
    if shown.returncode:
        return None
    try:
        return json.loads(shown.stdout).get("nid") or None
    except ValueError:
        return None


def departure_of(repo, prefix: str, arrival: Arrival, nid: str, token: str) -> str | None:
    """The commit in the source root that this arrival pairs with: the newest
    `MIGRATE: <kind> <stem> → <token>` under `prefix` (the root's repo-relative
    dir, "" for a root that is its repo) whose parent held `nid` at the path.
    `token` is the arrival's own root, the departure's `to`."""
    path = str(PurePosixPath(prefix, Event(arrival.kind, arrival.stem).path))
    log = _git(repo, "log", "--format=%H%x00%B%x1e", "--", path)
    if log.returncode:
        return None
    want = Departure(arrival.kind, arrival.stem, token)
    for record in log.stdout.decode().split("\x1e"):
        sha, _, message = record.strip("\n").partition("\0")
        if sha and want in parse_all(message) and nid_at(repo, f"{sha}^", path) == nid:
            return sha
    return None
