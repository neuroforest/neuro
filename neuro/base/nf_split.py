"""
Split a `.nf` root's repository into several, history and all.

`nfx.move` carries a module's files and leaves its history where it was made.
A split is for the other case - modules spun off into a root that is
distributed on its own: every commit and tag of those modules goes with them,
and the root they leave keeps none of it.

The source is partitioned, never rewritten in place. `plan` assigns every
module, by nid, to an *output*: the continuation (everything not named, with
the source's own `namespace.nfx` and its history) or one of the new trees.
`build` replays the source's commits oldest first into one new repository per
output under a staging directory: each output gets a commit wherever its share
of the tree changed, with the same author, dates and message, and every tag is
re-made on the commit that carries its document. `verify` proves nothing was
lost or duplicated. `swap` puts the outputs in place and keeps the source
aside.

What a split did is recorded in git and nowhere else:

- an event commit at each end (`nf_events.SplitOut` / `SplitIn`);
- a note on every new commit, in `refs/notes/nf-origin`: the source commit it
  was made from and the source's namespace nid - the old → new map, which
  travels with the repository;
- git's own `post-rewrite` hook, run in each output at the swap with the
  `old new` pairs, exactly as after a rebase.

Whoever keeps a graph of these repositories reads that. This module knows git.
"""

import dataclasses
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path, PurePosixPath

from neuro.base import nf_events, nf_history, nf_import, nf_repo, nfx, plugins
from neuro.base.index import NfxIndex
from neuro.utils import exceptions

NOTES_REF = nf_repo.NOTES_REF
STATE = "split.json"
KEPT = ".pre-split"
STAGING = ".split"
_STEP_LINE = re.compile(r"^(\S+) \S+ → \S+ \(re-pin")
_SUBJECT_LINE = re.compile(r"^[A-Z]+: (?:ontology|knowledge|metaontology) (\S+)")


class SplitRefused(Exception):
    def __init__(self, issues):
        super().__init__(f"{len(issues)} issue(s)")
        self.issues = list(issues)


@dataclasses.dataclass
class Output:
    """One part of the split. `to` None: the continuation, which takes the
    source's place. `modules` are the nids it holds at the source's head."""
    token: str
    to: Path | None = None
    name: str = ""
    description: str = ""
    modules: list[str] = dataclasses.field(default_factory=list)
    namespace: nfx.Nfx | None = None           # as its head will declare it
    needs: dict[str, list[str]] = dataclasses.field(default_factory=dict)  # token → "stem → dep" it pins there
    commits: int = 0
    tags: int = 0

    @property
    def word(self) -> str:
        return self.token or nf_events.ROOT_WORD


@dataclasses.dataclass
class Plan:
    source: nf_repo.Repo
    head: str
    branch: str
    token: str                    # the source's, and the continuation's
    outputs: list[Output]         # the continuation first
    owner: dict[str, str]         # module nid → output token; absent: the continuation
    stems: dict[str, tuple[str, str]]  # nid → (kind, stem) at the outputs' heads
    rules: dict[str, tuple[str, dict[str, str]]] = dataclasses.field(default_factory=dict)  # token → (prefix, {stem: new})
    renamed: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)  # token → {a source stem: the new one}
    commits: int = 0
    shared: int = 0               # source commits that became a commit in more than one output
    events: bool = True           # False: no event commit at either end - the histories do not speak of the split
    gone: dict[str, str] = dataclasses.field(default_factory=dict)   # nid of a module the head no longer has → token
    seen: set[str] = dataclasses.field(default_factory=set)          # every module nid the history holds

    def stem_for(self, token: str, stem: str) -> str | None:
        """The stem a module of `token` gets in place of `stem`, at whatever
        commit it had it; None when it keeps it."""
        prefix, explicit = self.rules.get(token, ("", {}))
        low = stem.lower()
        if low in explicit:
            return explicit[low]
        if prefix and low.startswith(prefix) and low != prefix:
            return low[len(prefix):]
        return None

    @property
    def restem(self) -> dict[str, str]:
        return {old: new for by in self.renamed.values() for old, new in by.items()}

    @property
    def continuation(self) -> Output:
        return self.outputs[0]

    @property
    def staging(self) -> Path:
        return self.source.root.parent / (self.source.root.name + STAGING)

    def dir_of(self, out: Output) -> Path:
        return self.staging / out.word / plugins.NF_DIRNAME


def _next_minor(version: str) -> str:
    major, minor = nf_repo.version_key(version)
    return f"{major}.{minor + 1}"


def plan(source: nf_repo.Repo, parts, others=(), with_dependants=False, rewrite_published=False,
         rename=None, events=True) -> Plan:
    """What splitting `source` writes. `parts`: one dict per new root -
    `token`, `to`, `modules` (stems, names or nids), optional `name`,
    `description` and `nid` (the namespace's, else minted). Everything not
    named stays in the continuation. Reads the repository; writes nothing.
    Raises `SplitRefused` with every reason.

    A part may rename its modules on the way - `rename` (`{module: stem}`)
    and `strip_prefix` (every stem that starts with it loses it). That is not
    an event: the new root's history is written as if the module had always
    had that stem - paths, the documents' `name`, tags, and the structured
    lines of messages. `rename` (`{stem: stem}`) does the same in the
    continuation, for a stem its modules have or once had.

    A module the head no longer has was made and deleted in the history; it
    has no owner and stays with the continuation unless a part names its nid
    under `gone`.

    `events` False leaves the event commits out: the continuation gets none,
    a new root's furniture arrives in a plain commit.

    A source with a remote has been published: its continuation is new
    history, every clone of it stops matching and the remote takes a
    force-push. That needs `rewrite_published`."""
    issues = []
    remotes = source.git("remote", check=False).split()
    if remotes and not rewrite_published:
        issues.append(f"{source.root} is published ({', '.join(remotes)}): the split rewrites its history, so every "
                      f"clone must be made again and the remote force-pushed - pass --rewrite-published to go ahead")
    if source.prefix:
        issues.append(f"{source.root} is a directory of {source.top}: a split needs a root that is its own repository")
    head = source.rev("HEAD")
    if head is None:
        raise SplitRefused([f"{source.root}: nothing committed yet"])
    if source.git("status", "--porcelain").strip():
        issues.append(f"{source.root} has uncommitted changes - commit or remove them first")
    if int(source.git("rev-list", "--merges", "--count", head).strip()):
        issues.append(f"{source.root} has merge commits: only a linear history can be partitioned")
    ns_path = source.root / nfx.NAMESPACE_FILENAME
    if not ns_path.is_file():
        raise SplitRefused(issues + [f"{source.root} has no {nfx.NAMESPACE_FILENAME}"])
    declared = nfx.read(ns_path)
    token = declared.namespace or ""

    idx = NfxIndex(*source._others(others, source.root), source.root)
    local = {e.nid: e for e in idx.entries() if e.tree == source.root}
    docs = {nid: nfx.read(e.path) for nid, e in local.items()}
    stems = {nid: (e.path.parent.name, e.path.stem) for nid, e in local.items()}

    def find(key):
        k = str(key).lower()
        k = Path(k).stem if k.endswith(".nfx") else k
        for nid, e in local.items():
            if k in (nid, e.path.stem.lower(), (docs[nid].name or "").lower()):
                return nid
        return None

    dependants: dict[str, set[str]] = {}
    for nid, doc in docs.items():
        for dep, _ in doc.dependencies:
            dependants.setdefault(dep, set()).add(nid)

    outputs = [Output(token, None, declared.name, declared.description or "")]
    owner: dict[str, str] = {}
    seen_tokens = {token}
    for part in parts:
        t = part.get("token")
        if t is None or not nfx.is_namespace_token(t) or t == nf_events.ROOT_WORD:
            issues.append(f"{t!r} is not a namespace token")
            continue
        if t in seen_tokens:
            issues.append(f"token {t or '∅'!r} is used twice (the source's is {token or '∅'!r})")
            continue
        if any(ns.token == t for ns in idx.namespaces()):
            issues.append(f"token {t!r} is already declared by another root in effect")
        seen_tokens.add(t)
        to = Path(part["to"]).expanduser().resolve() if part.get("to") else None
        if to is None or not plugins.is_consolidated(to):
            issues.append(f"{t}: the destination must be a directory named {plugins.NF_DIRNAME}")
        elif to.exists():
            issues.append(f"{t}: {to} already exists")
        elif not to.parent.is_dir():
            issues.append(f"{t}: {to.parent} does not exist")
        out = Output(t, to, part.get("name") or t, part.get("description") or "")
        todo = []
        for key in part.get("modules", ()):
            nid = find(key)
            if nid is None:
                issues.append(f"{t}: no module {key!r} in {source.root}")
            else:
                todo.append(nid)
        if not todo:
            issues.append(f"{t}: no modules")
        while todo:
            nid = todo.pop()
            if nid in owner:
                if owner[nid] != t:
                    issues.append(f"{stems[nid][1]} is assigned to both {owner[nid]} and {t}")
                continue
            owner[nid] = t
            out.modules.append(nid)
            if with_dependants:
                todo += sorted(dependants.get(nid, ()))
        outputs.append(out)
    outputs[0].modules = [nid for nid in local if nid not in owner]
    by_token = {o.token: o for o in outputs}

    gone: dict[str, str] = {}
    for part in parts:
        for key in part.get("gone") or ():
            try:
                nid = str(uuid.UUID(str(key)))
            except ValueError:
                issues.append(f"{part.get('token')}: gone {key!r} is not a nid")
                continue
            if nid in local:
                issues.append(f"{part.get('token')}: {stems[nid][1]} is still a module - name it under modules")
            elif gone.setdefault(nid, part.get("token")) != part.get("token"):
                issues.append(f"gone {nid} is assigned to both {gone[nid]} and {part.get('token')}")

    # renames on the way: a rule per part, applied to whatever stem its modules have at each commit
    rename_cont, rename = dict(rename or {}), {}
    rules: dict[str, tuple[str, dict[str, str]]] = {}
    nids: dict[str, str] = {}
    for part in parts:
        t = part.get("token")
        out = by_token.get(t)
        if out is None or out is outputs[0]:
            continue
        if part.get("nid"):
            try:
                nids[t] = str(uuid.UUID(str(part["nid"])))
            except ValueError:
                issues.append(f"{t}: nid {part['nid']!r} is not a UUID")
        wanted = {}
        prefix = part.get("strip_prefix") or ""
        for nid in out.modules if prefix else ():
            stem = stems[nid][1]
            if stem.startswith(prefix) and stem != prefix:
                wanted[nid] = stem[len(prefix):]
        for key, new in (part.get("rename") or {}).items():
            nid = find(key)
            if nid is None or owner.get(nid) != t:
                issues.append(f"{t}: rename names {key!r}, which is not one of its modules")
            else:
                wanted[nid] = new
        for nid, new in wanted.items():
            if not nf_events.is_stem(new):
                issues.append(f"{t}: {stems[nid][1]} → {new!r} is not a stem")
            elif new != stems[nid][1]:
                rename[nid] = new
        explicit = {stems[find(key)][1].lower(): new for key, new in (part.get("rename") or {}).items()
                    if find(key) in rename}
        if prefix or explicit:
            rules[t] = (prefix, explicit)
        taken: dict[str, str] = {}
        for nid in out.modules:
            final = rename.get(nid, stems[nid][1])
            if final.lower() in taken:
                issues.append(f"{t}: {stems[nid][1]} and {taken[final.lower()]} would both be named {final}")
            taken[final.lower()] = stems[nid][1]
    kept = {}
    for old, new in rename_cont.items():
        if not nf_events.is_stem(new):
            issues.append(f"{outputs[0].word}: {old} → {new!r} is not a stem")
            continue
        kept[str(old).lower()] = new
        nid = find(old)
        if nid is not None and nid not in owner:
            rename[nid] = new
    if kept:
        rules[token] = ("", kept)
    stems = {nid: (kind, rename.get(nid, stem)) for nid, (kind, stem) in stems.items()}

    # which output pins which: a module depending on one that lives elsewhere
    for nid, doc in docs.items():
        mine = owner.get(nid, token)
        for dep, _ in doc.dependencies:
            if dep in local and owner.get(dep, token) != mine:
                by_token[mine].needs.setdefault(owner.get(dep, token), []).append(
                    f"{stems[nid][1]} → {stems[dep][1]}")
    state: dict[str, int] = {}

    def cyclic(t, trail):
        if state.get(t) == 1:
            return trail[trail.index(t):] + [t]
        if state.get(t) == 2:
            return None
        state[t] = 1
        for n in by_token[t].needs:
            if n in by_token and (found := cyclic(n, trail + [t])):
                return found
        state[t] = 2
        return None

    for o in outputs:
        loop = cyclic(o.token, [])
        if loop:
            words = " → ".join(by_token[t].word for t in loop)
            issues.append(f"the parts would depend on each other: {words} - move the modules together "
                          f"(--with-dependants) or leave them")
            break
    if issues:
        raise SplitRefused(issues)

    # namespaces: the continuation keeps its own, bumped only when it now pins a new root
    cont = outputs[0]
    version = _next_minor(declared.version) if cont.needs else declared.version
    for out in outputs[1:]:
        out.namespace = nfx.Nfx(type=nfx.NAMESPACE_TYPE, nid=nids.get(out.token) or str(uuid.uuid4()),
                                version="1.0", name=out.name,
                                description=out.description or f"Split from {declared.name}",
                                namespace=out.token, dependencies=())
    for out in outputs[1:]:
        pins = list(declared.dependencies)
        for t in out.needs:
            pins.append((declared.nid, version) if t == token else (by_token[t].namespace.nid, "1.0"))
        out.namespace = dataclasses.replace(out.namespace, dependencies=tuple(pins))
    cont.namespace = dataclasses.replace(
        declared, version=version,
        dependencies=tuple(declared.dependencies) + tuple((by_token[t].namespace.nid, "1.0") for t in cont.needs))

    branch = source.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    p = Plan(source, head, branch, token, outputs, {**owner, **gone}, stems, rules, events=events, gone=gone)
    _count(p)
    issues = [f"{t}: gone {nid} is in no commit of {source.root}" for nid, t in gone.items() if nid not in p.seen]
    issues += [f"{outputs[0].word}: no module of it ever had the stem {old}" for old in kept
               if old not in p.renamed.get(token, {})]
    if issues:
        raise SplitRefused(issues)
    return p


# ---- the walk ------------------------------------------------------------------------


def _walk(p: Plan):
    """Every source commit, oldest first, with its tree sorted by output:
    `(sha, {token: {path: (mode, blob)}}, {(kind, stem): token}, edits)`. A
    module's `.nfx` is assigned by its nid, its validators and test by its
    stem; everything else - the declaration, the hooks, the furniture - stays
    with the continuation.

    A renamed module's files sit at their new paths, under the source's blobs.
    `edits` - `{token: {path: (what, old, new)}}` - names the ones whose
    content must follow (`nfx`: the document's name; `test`: the validators
    path in it). `owners` keeps the source's stems: tags and messages are read
    in those."""
    repo, default = p.source, p.token
    cat = nf_history._Cat(repo.top)
    nid_of: dict[str, str | None] = {}
    try:
        for sha in repo.git("rev-list", "--reverse", p.head).split():
            entries = []
            for line in repo.git("ls-tree", "-r", sha).splitlines():
                meta, path = line.split("\t", 1)
                mode, _type, blob = meta.split()
                entries.append((mode, blob, PurePosixPath(path)))
            owners: dict[tuple[str, str], str] = {}
            here: dict[str, str] = {}                      # this commit's stem → the one it gets
            for _mode, blob, path in entries:
                if len(path.parts) == 2 and path.parts[0] in nf_events.KINDS and path.suffix == ".nfx":
                    if blob not in nid_of:
                        nid_of[blob] = (cat.json(blob) or {}).get("nid")
                        if nid_of[blob]:
                            p.seen.add(nid_of[blob])
                    t = owners[(path.parts[0], path.stem.lower())] = p.owner.get(nid_of[blob], default)
                    new = p.stem_for(t, path.stem)
                    if new:
                        here[path.stem.lower()] = new
                        p.renamed.setdefault(t, {})[path.stem.lower()] = new
            by_stem = {stem: t for (_kind, stem), t in owners.items()}
            trees: dict[str, dict[str, tuple[str, str]]] = {o.token: {} for o in p.outputs}
            edits: dict[str, dict[str, tuple[str, str, str]]] = {o.token: {} for o in p.outputs}
            for mode, blob, path in entries:
                t, edit = default, None
                if len(path.parts) == 2 and path.suffix == ".nfx" and path.parts[0] in nf_events.KINDS:
                    t = owners[(path.parts[0], path.stem.lower())]
                    if path.stem.lower() in here:
                        edit = ("nfx", path.stem, here[path.stem.lower()])
                        path = path.with_name(f"{edit[2]}.nfx")
                elif len(path.parts) == 2 and path.suffix == ".py":
                    if path.parts[0] == plugins._VALIDATORS_DIR:
                        t = by_stem.get(path.stem.lower(), default)
                        if path.stem.lower() in here:
                            path = path.with_name(f"{here[path.stem.lower()]}.py")
                    elif path.parts[0] == "tests" and path.stem.startswith("test_"):
                        stem = path.stem[5:]
                        t = by_stem.get(stem.lower(), default)
                        if stem.lower() in here:
                            edit = ("test", stem, here[stem.lower()])
                            path = path.with_name(f"test_{edit[2]}.py")
                if str(path) in trees[t]:
                    raise SplitRefused([f"{sha[:7]}: two files would be {path} in "
                                        f"{t or nf_events.ROOT_WORD} - the rename collides in the history"])
                trees[t][str(path)] = (mode, blob)
                if edit:
                    edits[t][str(path)] = edit
            yield sha, trees, owners, edits
    finally:
        cat.close()


def _changed(trees, previous) -> list[str]:
    """The outputs whose share differs from the commit before; `previous` is updated in place."""
    changed = [t for t, tree in trees.items() if previous.get(t, {}) != tree]
    for t in changed:
        previous[t] = trees[t]
    return changed


def _tags(repo):
    """Every tag: `(name, commit, tagger, date, message)`; `tagger` None for a lightweight one."""
    fmt = "%(refname:short)%00%(objecttype)%00%(*objectname)%00%(objectname)%00%(taggername) %(taggeremail)" \
          "%00%(taggerdate:raw)%00%(contents)%1e"
    out = []
    for record in repo.git("for-each-ref", "refs/tags", f"--format={fmt}").split("\x1e"):
        record = record.lstrip("\n")
        if not record:
            continue
        name, kind, peeled, obj, tagger, date, message = record.split("\0", 6)
        if kind == "tag":
            out.append((name, peeled, tagger, date, message))
        else:
            out.append((name, obj, None, None, None))
    return out


def _tag_owner(name, owners, series, default) -> str:
    """The output a tag belongs to: the one holding its document at the tagged
    commit - or, for a tag `nfx.rename` re-made under a later stem, the one
    that holds that series where it last existed (`series`)."""
    parsed = nf_repo.parse_tag(name)
    if parsed is None or parsed[0][0] == "namespace":
        return default
    key = (parsed[0][0], parsed[0][1].lower())
    return owners.get(key) or series.get(key, default)


def _count(p: Plan) -> None:
    """Fill the plan's counts: commits and tags per output, commits shared between outputs."""
    previous: dict[str, dict] = {}
    commits = {o.token: 0 for o in p.outputs}
    owners_at, series = {}, {}
    p.commits = p.shared = 0
    for sha, trees, owners, _edits in _walk(p):
        changed = _changed(trees, previous) or [p.token]
        for t in changed:
            commits[t] += 1
        p.commits += 1
        p.shared += len(changed) > 1
        owners_at[sha] = owners
        series.update(owners)
    tags = {o.token: 0 for o in p.outputs}
    for name, commit, *_ in _tags(p.source):
        tags[_tag_owner(name, owners_at.get(commit, {}), series, p.token)] += 1
    for out in p.outputs:
        out.commits, out.tags = commits[out.token], tags[out.token]


# ---- build ------------------------------------------------------------------------------


def _message(message: str, mine: set[str], theirs: set[str]) -> str:
    """The commit message for one output: the subject as it was, the body
    without the lines that speak of documents now living in another output."""
    subject, _, body = message.strip("\n").partition("\n")
    kept = []
    for line in body.split("\n"):
        stem = None
        event = nf_events.parse(line.split(" · ", 1)[0].strip())
        if isinstance(event, nf_events.Event):
            stem = event.stem
        elif m := _STEP_LINE.match(line) or _SUBJECT_LINE.match(line):
            stem = m[1]
        if stem is not None and stem.lower() in theirs and stem.lower() not in mine:
            continue
        kept.append(line)
    body = "\n".join(kept).strip("\n")
    return f"{subject}\n\n{body}\n" if body else f"{subject}\n"


_STRUCTURED = re.compile(r"^(?:[A-Z]+: )?(?:ontology|knowledge|metaontology)[ /]")


def _restem(text: str, restem: dict[str, str]) -> str:
    """`text` with the renamed stems replaced, in the lines that have a known
    form - `VERB: <kind> <stem> …` and a tag's `<kind>/<stem>/<version> …`.
    Free prose is left as it was written."""
    if not restem:
        return text
    word = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(sorted(map(re.escape, restem), key=len, reverse=True))
                      + r")(?![A-Za-z0-9-])")
    return "\n".join(word.sub(lambda m: restem[m[1]], line)
                     if _STRUCTURED.match(line) or _STEP_LINE.match(line) else line
                     for line in text.split("\n"))


def _unprefix(text: str, prefix: str, renamed: dict[str, str]) -> str:
    """`text` as one output words it: a stem that lost the output's prefix
    loses it wherever it is written, prose included. Only there - elsewhere
    `<prefix><stem>` is how another root names that module."""
    own = [old for old, new in renamed.items() if prefix and old == prefix + new]
    if not own:
        return text
    word = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(sorted(map(re.escape, own), key=len, reverse=True))
                      + r")(?![A-Za-z0-9-])")
    return word.sub(lambda m: renamed[m[1]], text)


FURNITURE_SUBJECT = "ADD: hooks and lint configuration"


def _retag(name: str, restem: dict[str, str]) -> str:
    parsed = nf_repo.parse_tag(name)
    if parsed is None or parsed[0][0] == "namespace" or parsed[0][1].lower() not in restem:
        return name
    return nf_repo.tag_name((parsed[0][0], restem[parsed[0][1].lower()]), parsed[1])


def _run(cwd, *args, env=None, data=None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, env=env, input=data, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def _tree(repo_dir, entries, env) -> str:
    index = Path(repo_dir) / ".git" / "split-index"
    index.unlink(missing_ok=True)
    env = {**env, "GIT_INDEX_FILE": str(index)}
    _run(repo_dir, "update-index", "--add", "--index-info", env=env,
         data="".join(f"{mode} {blob}\t{path}\n" for path, (mode, blob) in sorted(entries.items())))
    tree = _run(repo_dir, "write-tree", env=env).strip()
    index.unlink(missing_ok=True)
    return tree


def _fi_data(text: str) -> bytes:
    raw = text.encode()
    return b"data %d\n%s\n" % (len(raw), raw)


def build(p: Plan, progress=None) -> dict:
    """Write one repository per output under `p.staging` (which must not
    exist) and the state file `swap` reads. Returns the state."""
    if p.staging.exists():
        raise FileExistsError(f"{p.staging} exists - a split is staged there; swap it or remove it")
    repo, env = p.source, os.environ.copy()
    for var in nf_repo._GIT_PATH_VARS:
        env.pop(var, None)
    objects = Path(repo.git("rev-parse", "--git-path", "objects").strip())
    objects = objects if objects.is_absolute() else (repo.top / objects).resolve()
    dirs = {o.token: p.dir_of(o) for o in p.outputs}
    ns_blob = {}
    for out in p.outputs:
        d = dirs[out.token]
        d.mkdir(parents=True)
        _run(d, "init", "-q", "-b", p.branch, env=env)
        (d / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
        (d / ".git" / "objects" / "info" / "alternates").write_text(f"{objects}\n")
        for key in ("user.name", "user.email"):
            value = repo.git("config", "--local", "--get", key, check=False).strip()
            if value:
                _run(d, "config", key, value, env=env)
        ns_blob[out.token] = _run(d, "hash-object", "-w", "--stdin", env=env, data=nfx.dumps(out.namespace)).strip()

    meta = {}
    fmt = "%H%x00%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd%x00%B%x1e"
    for record in repo.git("log", "--date=raw", f"--format={fmt}", p.head).split("\x1e"):
        record = record.lstrip("\n")
        if record:
            sha, an, ae, ad, cn, ce, cd, message = record.split("\0", 7)
            meta[sha] = (an, ae, ad, cn, ce, cd, message)

    previous: dict[str, dict] = {}
    heads: dict[str, str] = {}
    first: dict[str, tuple[str, str]] = {}          # token → (its first commit, that commit's committer line)
    at: dict[str, dict[str, str | None]] = {t: {} for t in dirs}
    pairs: dict[str, list[tuple[str, str]]] = {t: [] for t in dirs}
    owners_at, series = {}, {}
    rewritten: dict[tuple, str] = {}                 # (token, blob, edit) → the blob written in its place
    blobs: dict[str, dict[str, str]] = {t: {} for t in dirs}   # token → {new blob: the source's}
    unedited: list[str] = []
    latest: dict[str, dict] = {}                     # token → its tree as last written, edits applied
    restem = p.restem                                # complete: `plan` walked the history once

    def worded(t, text):
        return _unprefix(_restem(text, restem), p.rules.get(t, ("", {}))[0], p.renamed.get(t, {}))

    def edited(t, path, blob, edit):
        key = (t, blob, edit)
        if key not in rewritten:
            what, old, new = edit
            raw = subprocess.run(["git", "cat-file", "blob", blob], cwd=repo.top, env=env, capture_output=True,
                                 check=True).stdout
            try:
                out = (nf_import.rename_to_stem(raw, new)[0] if what == "nfx"
                       else nf_repo.rename_test(raw.decode(), old, new).encode())
            except ValueError as e:
                unedited.append(f"{path} ({blob[:7]}): {e}")
                out = raw
            r = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=dirs[t], env=env, input=out,
                               capture_output=True, check=True)
            rewritten[key] = r.stdout.decode().strip()
            if rewritten[key] != blob:
                blobs[t][rewritten[key]] = blob
        return rewritten[key]

    shas = repo.git("rev-list", "--reverse", p.head).split()
    for i, (sha, trees, owners, edits) in enumerate(_walk(p), start=1):
        owners_at[sha] = owners
        series.update(owners)
        an, ae, ad, cn, ce, cd, message = meta[sha]
        changed = _changed(trees, previous) or [p.token]
        stems_of: dict[str, set[str]] = {t: set() for t in dirs}
        for (_kind, stem), t in owners.items():
            stems_of[t].add(stem)
        for t in changed:
            entries = dict(trees[t])
            for path, edit in edits[t].items():
                entries[path] = (entries[path][0], edited(t, path, entries[path][1], edit))
            latest[t] = dict(entries)
            if t != p.token:
                entries[nfx.NAMESPACE_FILENAME] = ("100644", ns_blob[t])
            tree = _tree(dirs[t], entries, env)
            theirs = set().union(*(s for o, s in stems_of.items() if o != t))
            cenv = {**env, "GIT_AUTHOR_NAME": an, "GIT_AUTHOR_EMAIL": ae, "GIT_AUTHOR_DATE": ad,
                    "GIT_COMMITTER_NAME": cn, "GIT_COMMITTER_EMAIL": ce, "GIT_COMMITTER_DATE": cd}
            parent = ["-p", heads[t]] if t in heads else []
            new = _run(dirs[t], "commit-tree", tree, *parent, "-F", "-", env=cenv,
                       data=worded(t, _message(message, stems_of[t], theirs))).strip()
            heads[t] = new
            first.setdefault(t, (new, f"{cn} <{ce}> {cd}"))
            pairs[t].append((sha, new))
        for t in dirs:
            at[t][sha] = heads.get(t)
        if progress:
            progress(i, len(shas))
    empty = [by.word for by in p.outputs if by.token not in heads]
    if empty:
        shutil.rmtree(p.staging)
        raise SplitRefused([f"{w}: no commit of the source touches its modules" for w in empty])

    # the event commit at each end, then the furniture a new root needs to stand alone
    source_ns = nfx.read(repo.root / nfx.NAMESPACE_FILENAME)
    furniture = {path: entry for path, entry in previous[p.token].items()
                 if path != nfx.NAMESPACE_FILENAME
                 and PurePosixPath(path).parts[0] not in (*nf_events.KINDS, plugins._VALIDATORS_DIR, "tests")}
    cont = p.continuation
    extra_tags = []                                # (token, name, commit, message)
    for out in p.outputs[1:]:
        t = out.token
        entries = {**latest[t], **furniture, nfx.NAMESPACE_FILENAME: ("100644", ns_blob[t])}
        tree = _tree(dirs[t], entries, env)
        subject = nf_events.SplitIn(p.token).subject if p.events else FURNITURE_SUBJECT
        heads[t] = _run(dirs[t], "commit-tree", tree, "-p", heads[t], "-F", "-", env=env,
                        data=subject + "\n").strip()
        name = nf_import.namespace_tag(t, "1.0")
        extra_tags.append((t, name, first[t][0],
                           f"{name} — the root's declaration, in every commit"
                           + (f" · split from {cont.word}" if p.events else "")))
    if not p.events and cont.namespace.version != source_ns.version:
        entries = {**latest[p.token], nfx.NAMESPACE_FILENAME: ("100644", ns_blob[p.token])}
        pins = ", ".join(by.word for by in p.outputs[1:] if by.token in cont.needs)
        heads[p.token] = _run(dirs[p.token], "commit-tree", _tree(dirs[p.token], entries, env), "-p", heads[p.token],
                              "-F", "-", env=env, data=f"UPDATE: namespace pins {pins}\n").strip()
        name = nf_import.namespace_tag(p.token, cont.namespace.version)
        extra_tags.append((p.token, name, heads[p.token], f"{name} — pins {pins}"))
    for n, out in enumerate(p.outputs[1:] if p.events else (), start=1):
        entries = dict(latest[p.token])
        last = n == len(p.outputs) - 1
        if last and cont.namespace.version != source_ns.version:
            entries[nfx.NAMESPACE_FILENAME] = ("100644", ns_blob[p.token])
        tree = _tree(dirs[p.token], entries, env)
        body = "\n".join(sorted(f"{p.stems[nid][0]} {p.stems[nid][1]}" for nid in out.modules))
        heads[p.token] = _run(dirs[p.token], "commit-tree", tree, "-p", heads[p.token], "-F", "-", env=env,
                              data=f"{nf_events.SplitOut(out.token).subject}\n\n{body}\n").strip()
        if last and cont.namespace.version != source_ns.version:
            name = nf_import.namespace_tag(p.token, cont.namespace.version)
            extra_tags.append((p.token, name, heads[p.token],
                               f"{name} — pins {', '.join(by.word for by in p.outputs[1:] if by.token in cont.needs)}"
                               f" · {nf_events.SplitOut(out.token).subject}"))

    # tags and notes, one fast-import per output
    ident = _run(repo.top, "var", "GIT_COMMITTER_IDENT", env=env).strip()
    streams: dict[str, list[bytes]] = {t: [] for t in dirs}
    skipped = []
    for name, commit, tagger, date, message in _tags(repo):
        t = _tag_owner(name, owners_at.get(commit, {}), series, p.token)
        target = at[t].get(commit)
        if target is None:
            skipped.append(f"{name}: its commit {commit[:7]} has no counterpart in {p.continuation.word if t == p.token else t}")
            continue
        name, message = _retag(name, p.renamed.get(t, {})), message and worded(t, message)
        if tagger is None:
            streams[t] += [b"reset refs/tags/%s\n" % name.encode(), b"from %s\n\n" % target.encode()]
        else:
            streams[t] += [b"tag %s\n" % name.encode(), b"from %s\n" % target.encode(),
                           b"tagger %s %s\n" % (tagger.encode(), date.encode()), _fi_data(message)]
    for t, name, commit, message in extra_tags:
        tagger = first[t][1] if name == nf_import.namespace_tag(t, "1.0") and t != p.token else ident
        streams[t] += [b"tag %s\n" % name.encode(), b"from %s\n" % commit.encode(),
                       b"tagger %s\n" % tagger.encode(), _fi_data(message + "\n")]
    for t, d in dirs.items():
        stream = streams[t]
        stream += [b"commit %s\n" % NOTES_REF.encode(), b"committer %s\n" % ident.encode(),
                   _fi_data(f"Notes: the {source_ns.nid} commit each commit was split from\n")]
        for old, new in pairs[t]:
            stream += [b"N inline %s\n" % new.encode(), _fi_data(f"{old} {source_ns.nid}\n")]
        stream.append(b"\ndone\n")
        r = subprocess.run(["git", "fast-import", "--quiet", "--done"], cwd=d, env=env, input=b"".join(stream),
                           capture_output=True)
        if r.returncode:
            raise RuntimeError(f"git fast-import in {d}: {r.stderr.decode(errors='replace').strip()}")
        _run(d, "update-ref", f"refs/heads/{p.branch}", heads[t], env=env)
        _run(d, "repack", "-a", "-d", "-q", env=env)
        (d / ".git" / "objects" / "info" / "alternates").unlink()
        _run(d, "fsck", "--connectivity-only", env=env)
        _run(d, "reset", "--hard", "-q", env=env)

    remotes = [line.split(" ", 1) for line in repo.git("config", "--local", "--get-regexp", r"^(remote|branch)\.",
                                                       check=False).splitlines() if " " in line]
    state = {
        "source": str(repo.root), "head": p.head, "branch": p.branch, "namespace": source_ns.nid,
        "remotes": remotes, "skipped_tags": skipped, "unedited": unedited,
        "outputs": [{"token": o.token, "word": o.word, "dir": str(dirs[o.token]),
                     "to": str(o.to) if o.to else str(repo.root), "head": heads[o.token],
                     "modules": sorted(p.stems[n][1] for n in o.modules),
                     "renamed": dict(sorted(p.renamed.get(o.token, {}).items())),
                     "pairs": f"{o.word}.pairs", "blobs": f"{o.word}.blobs"} for o in p.outputs],
    }
    for o in p.outputs:
        (p.staging / f"{o.word}.pairs").write_text("".join(f"{old} {new}\n" for old, new in pairs[o.token]))
        (p.staging / f"{o.word}.blobs").write_text("".join(f"{new} {old}\n" for new, old in blobs[o.token].items()))
    (p.staging / STATE).write_text(json.dumps(state, indent=2) + "\n")
    return state


# ---- verify -------------------------------------------------------------------------------


def _ls(repo_dir, rev) -> dict[str, str]:
    out = {}
    for line in _run(repo_dir, "ls-tree", "-r", rev).splitlines():
        meta, path = line.split("\t", 1)
        out[path] = meta.split()[2]
    return out


def verify(staging, others=()) -> list[str]:
    """What is wrong with a staged split, read back from the repositories it
    wrote: at every source commit the outputs' trees together must equal the
    source's, with no path in two of them; every source tag must exist in
    exactly one output, on a commit that holds its document at that version;
    and the heads, read together, must be sound documents with pins that hold."""
    staging = Path(staging)
    state = json.loads((staging / STATE).read_text())
    source = Path(state["source"])
    outputs = state["outputs"]
    cont = outputs[0]["word"]
    issues = []

    # a renamed module is read back under the source's path and blob
    back, restem = {}, {}
    for o in outputs:
        renamed = o.get("renamed") or {}
        restem.update(renamed)
        paths = {}
        for old, new in renamed.items():
            for kind in nf_events.KINDS:
                paths[f"{kind}/{new}.nfx"] = f"{kind}/{old}.nfx"
            paths[f"{plugins._VALIDATORS_DIR}/{new}.py"] = f"{plugins._VALIDATORS_DIR}/{old}.py"
            paths[f"tests/test_{new}.py"] = f"tests/test_{old}.py"
        blobs = dict(line.split() for line in (staging / o["blobs"]).read_text().splitlines()) if o.get("blobs") else {}
        back[o["word"]] = (paths, blobs)
    issues += [f"left as it was, the rename could not be written into it: {u}" for u in state.get("unedited", ())]

    cache: dict[tuple[str, str], dict[str, str]] = {}
    position = {o["word"]: 0 for o in outputs}
    pairs = {o["word"]: [line.split() for line in (staging / o["pairs"]).read_text().splitlines()] for o in outputs}
    current: dict[str, str | None] = {o["word"]: None for o in outputs}
    for sha in _run(source, "rev-list", "--reverse", state["head"]).split():
        for o in outputs:
            w = o["word"]
            if position[w] < len(pairs[w]) and pairs[w][position[w]][0] == sha:
                current[w] = pairs[w][position[w]][1]
                position[w] += 1
        merged: dict[str, str] = {}
        for o in outputs:
            w = o["word"]
            if current[w] is None:
                continue
            if (w, current[w]) not in cache:
                paths, blobs = back[w]
                cache[(w, current[w])] = {paths.get(path, path): blobs.get(blob, blob)
                                          for path, blob in _ls(o["dir"], current[w]).items()}
            for path, blob in cache[(w, current[w])].items():
                if w != cont and path == nfx.NAMESPACE_FILENAME:
                    continue
                if path in merged:
                    issues.append(f"{sha[:7]}: {path} is in two outputs")
                merged[path] = blob
        if merged != _ls(source, sha):
            want = _ls(source, sha)
            lost = sorted(set(want) - set(merged))[:3]
            extra = sorted(set(merged) - set(want))[:3]
            differ = sorted(k for k in set(want) & set(merged) if want[k] != merged[k])[:3]
            issues.append(f"{sha[:7]}: the outputs do not add up to the source "
                          f"(lost {lost}, extra {extra}, differ {differ})")
    for o in outputs:
        if position[o["word"]] != len(pairs[o["word"]]):
            issues.append(f"{o['word']}: {len(pairs[o['word']]) - position[o['word']]} commit(s) come from no source commit")

    want = set(_run(source, "tag").split()) - {s.split(":", 1)[0] for s in state["skipped_tags"]}
    have: dict[str, list[str]] = {}                # by the source's name for the tag
    # what the source already had wrong is not the split's doing
    known = set(nf_history.check_tags(source))
    if restem:
        word = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(sorted(map(re.escape, restem), key=len, reverse=True))
                          + r")(?![A-Za-z0-9-])")
        known |= {word.sub(lambda m: restem[m[1]], k) for k in known}
    for o in outputs:
        renamed = o.get("renamed") or {}
        olds: dict[str, list[str]] = {}
        for old, new in renamed.items():
            olds.setdefault(new, []).append(old)
        for name in _run(o["dir"], "tag").split():
            parsed = nf_repo.parse_tag(name)
            # a renamed series is read back under the stem the source has that tag for
            names = [n for n in (nf_repo.tag_name((parsed[0][0], old), parsed[1])
                                 for old in olds.get(parsed[0][1], ())) if n in want] \
                if parsed and parsed[0][0] != "namespace" else []
            for n in names or [name]:
                have.setdefault(n, []).append(o["word"])
        issues += [f"{o['word']}: {i}" for i in nf_history.check_tags(o["dir"]) if i not in known]
    issues += [f"tag {name} is in no output" for name in sorted(want - set(have))]
    issues += [f"tag {name} is in {', '.join(where)}" for name, where in sorted(have.items())
               if len(where) > 1 and not name.startswith("namespace/")]
    issues += [f"tag {s}" for s in state["skipped_tags"]]

    trees = [Path(o["dir"]).resolve() for o in outputs]
    rest = []
    for r in (Path(r).resolve() for r in others):
        ns = r / nfx.NAMESPACE_FILENAME
        # the source itself, and any other checkout of its namespace, is what the continuation replaces
        if r != source.resolve() and not (ns.is_file() and nfx.read(ns).nid == state["namespace"]):
            rest.append(r)
    try:
        idx = NfxIndex(*rest, *trees)
        for o, root in zip(outputs, trees):
            issues += [f"{o['word']}: {nfx.NAMESPACE_FILENAME}: {f}"
                       for f in nf_repo.namespace_failures(idx, root / nfx.NAMESPACE_FILENAME)]
        for e in idx.entries():
            if e.tree in trees:
                where = f"{e.tree.parent.name}: {e.path.relative_to(e.tree)}"
                issues += [f"{where}: {f}" for f in nf_repo.document_failures(idx, e.path)]
                issues += [f"{where}: {f}" for f in idx.check_dependency_versions(e.path)]
    except exceptions.NfxViolation as e:  # trees that cannot be indexed together are the finding
        issues.append(f"the outputs do not index together: {e}")
    return issues


# ---- swap ---------------------------------------------------------------------------------


def swap(staging, notify=True) -> dict:
    """Put a staged split in place: the source is kept as `<root>.pre-split`,
    the continuation takes its path, each new root goes to its destination.
    The hooks are installed as the source had them, its remotes carried to the
    continuation, and - `notify` - git's `post-rewrite` hook is run in each
    output with its `old new` pairs. Pushes nothing. Returns the state, with
    `kept` added."""
    staging = Path(staging)
    state = json.loads((staging / STATE).read_text())
    source = Path(state["source"])
    repo = nf_repo.Repo(source)
    problems = []
    if repo.rev("HEAD") != state["head"]:
        problems.append(f"{source} has moved since the split was built ({state['head'][:7]}) - build it again")
    if repo.git("status", "--porcelain").strip():
        problems.append(f"{source} has uncommitted changes")
    kept = source.parent / (source.name + KEPT)
    if kept.exists():
        problems.append(f"{kept} exists - remove or rename the previous backup first")
    for o in state["outputs"][1:]:
        if Path(o["to"]).exists():
            problems.append(f"{o['to']} already exists")
    if problems:
        raise SplitRefused(problems)

    env = os.environ.copy()
    for var in nf_repo._GIT_PATH_VARS:
        env.pop(var, None)
    source.rename(kept)
    for o in state["outputs"]:
        shutil.move(o["dir"], o["to"])
    for key, value in state["remotes"]:
        _run(state["outputs"][0]["to"], "config", key, value, env=env)
    for o in state["outputs"]:
        nf_repo.Repo(o["to"]).track_notes()
        if notify:
            subprocess.run(["git", "hook", "run", "--ignore-missing", f"--to-stdin={staging / o['pairs']}",
                            "post-rewrite", "--", "rebase"], cwd=o["to"], env=env, capture_output=True)
    shutil.rmtree(staging)
    state["kept"] = str(kept)
    return state
