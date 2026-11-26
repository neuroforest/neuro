"""
Plugin file discovery and indexing.

`PluginIndex` is the generic base; subclasses set a `KIND` tuple to restrict
the view to one or more `type` values from the on-disk `.nfx`. With `KIND = ()`
the index accepts every type - `NfxIndex` is that unrestricted view.
`OntologyIndex` accepts ontology + metaontology; `KnowledgeIndex` accepts
knowledge.

Discovery is delegated to `neuro.base.plugins.walk_plugins`. Validators are
loaded once per validators file via `plugins.load_validators`. Implicit parent
dependencies (nested-plugin "ontology import" semantics) are computed at
register time and surfaced via `Entry.implicit_parent_nid`; `_topo` /
`NfxTree` callers obtain them through the index's `extra_deps` callable.

Three things are fatal at scan time: a nid claimed by two
files anywhere; a local name (file stem, case-insensitive) used twice inside
one registry root - across roots it may repeat, the roots' namespaces tell
them apart; and, in a consolidated root, a file whose
kind subdir disagrees with its `type` field.

Before the modules, a pre-pass reads each consolidated root's `namespace.nfx`
into a `Namespace`; every `Entry` of that root carries its
token and nid. Fatal there: a declaration that is not `type: "namespace"` or
fails `nfx.namespace_issues`, two roots claiming one token, a namespace nid
also claimed elsewhere. A missing declaration is a warning and leaves the
root's entries with `namespace None` until `tree.import` writes one
a legacy root never has one.
"""

import dataclasses
import logging
from dataclasses import dataclass
from pathlib import Path

from neuro.base import nfx, plugins
from neuro.utils import exceptions

# The `type` values a kind subdir admits. `ontology/` holds the metaontology
# too - in the app's own root it is the one module there -
# until `metaontology` turns from a type into a property.
_KIND_TYPES = {
    "ontology": ("ontology", "metaontology"),
    "knowledge": ("knowledge",),
}


@dataclass(frozen=True)
class Namespace:
    """One root's `namespace.nfx`, read.

    `token` is the written token - "" for the root namespace - and
    `dependencies` the envelope: `(nid, version)` pins on other namespace
    files. `was` lists the tokens this root retired.
    """
    root: Path
    path: Path
    nid: str
    token: str
    version: str
    name: str
    was: tuple[str, ...] = ()
    dependencies: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Entry:
    path: Path
    nid: str
    type: str
    name: str
    version: str
    plugin_root: Path | None = None
    parent_plugin_root: Path | None = None
    implicit_parent_nid: str | None = None
    registry_root: Path | None = None
    validators_path: Path | None = None
    namespace: str | None = None
    namespace_nid: str | None = None

    @property
    def local_name(self) -> str:
        """The module's name inside its root - the file stem."""
        return self.path.stem


class PluginIndex:
    """Index of `.nfx` files discovered from PLUGINS registry roots, filtered
    by the subclass's `KIND` tuple (empty = accept all types).

    Keyed canonically by `nid`. `resolve()` additionally accepts name, stem,
    or filename via priority-ordered fallback. Pure file-level discovery -
    no database access.
    """

    KIND: tuple[str, ...] = ()

    def __init__(self, *roots):
        self._index: dict[str, Entry] = {}
        self._by_plugin_root: dict[Path, Entry] = {}
        self._by_local_name: dict[tuple[Path, str], Path] = {}
        self._namespaces: dict[Path, Namespace] = {}
        self._roots = tuple(Path(r).resolve() for r in roots)
        self._read_namespaces()
        self._scan()
        self._resolve_implicit_parents()

    # ---- registration ----------------------------------------------------------

    def _read_namespaces(self) -> None:
        """Pre-pass: one `Namespace` per consolidated root that declares one."""
        by_token: dict[str, Path] = {}
        by_nid: dict[str, Path] = {}
        for root in self._roots:
            path = plugins.namespace_path(root)
            if path is None:
                continue
            if not path.is_file():
                if root.is_dir():
                    logging.warning(f"{root}: no {nfx.NAMESPACE_FILENAME}, its modules carry no namespace")
                continue
            doc = nfx.read(path)
            if not doc.is_namespace:
                raise exceptions.NfxViolation(
                    f"{path} is reserved for the namespace declaration but declares type {doc.type!r}"
                )
            issues = nfx.namespace_issues(doc)
            if issues:
                raise exceptions.NfxViolation(f"{path}: " + "; ".join(issues))
            if not doc.nid:
                raise exceptions.NfxViolation(f"{path} declares no nid")
            claimed = by_token.get(doc.namespace)
            if claimed is not None:
                raise exceptions.NfxViolation(
                    f"namespace token collision: {doc.namespace!r} declared by {claimed} and {path}"
                )
            if doc.nid in by_nid:
                raise exceptions.NfxViolation(
                    f"nid collision: {doc.nid} claimed by {by_nid[doc.nid]} and {path}"
                )
            by_token[doc.namespace] = path
            by_nid[doc.nid] = path
            self._namespaces[root] = Namespace(
                root=root,
                path=path,
                nid=doc.nid,
                token=doc.namespace,
                version=doc.version,
                name=doc.name,
                was=tuple(doc.was),
                dependencies=tuple(doc.dependencies),
            )

    def _register(self, pf: plugins.PluginFile) -> Entry | None:
        path = pf.nfx_path
        doc = nfx.read(path)
        if doc.is_namespace:
            raise exceptions.NfxViolation(
                f"{path} is a namespace declaration; only <root>/{nfx.NAMESPACE_FILENAME} of a .nf root may be one"
            )
        if not doc.nid:
            return None
        if pf.expected_type and doc.type not in _KIND_TYPES[pf.expected_type]:
            raise exceptions.NfxViolation(
                f"{path} sits in {pf.expected_type}/ but declares type {doc.type!r}"
            )
        if self.KIND and doc.type not in self.KIND:
            return None
        existing = self._index.get(doc.nid)
        if existing and existing.path != path:
            raise exceptions.NfxViolation(
                f"nid collision: {doc.nid} claimed by {existing.path} and {path}"
            )
        for ns in self._namespaces.values():
            if ns.nid == doc.nid:
                raise exceptions.NfxViolation(
                    f"nid collision: {doc.nid} claimed by {ns.path} and {path}"
                )
        name_key = (pf.registry_root, path.stem.lower())
        claimed = self._by_local_name.get(name_key)
        if claimed is not None and claimed != path:
            raise exceptions.NfxViolation(
                f"local name collision in {pf.registry_root}: {path.stem!r} claimed by {claimed} and {path}"
            )
        ns = self._namespaces.get(pf.registry_root)
        entry = Entry(
            path=path,
            nid=doc.nid,
            type=doc.type,
            name=doc.name,
            version=doc.version,
            plugin_root=pf.plugin_root,
            parent_plugin_root=pf.parent_plugin_root,
            registry_root=pf.registry_root,
            validators_path=pf.validators_path,
            namespace=None if ns is None else ns.token,
            namespace_nid=None if ns is None else ns.nid,
        )
        self._index[doc.nid] = entry
        self._by_local_name[name_key] = path
        if pf.plugin_root is not None:
            self._by_plugin_root[pf.plugin_root.resolve()] = entry
        return entry

    def _scan(self) -> None:
        for pf in plugins.walk_plugins(self._roots):
            self._register(pf)
            plugins.load_validators(pf)

    def _resolve_implicit_parents(self) -> None:
        """Second pass: each entry whose path has a parent plugin root gets
        its `implicit_parent_nid` set to that parent plugin's same-kind nid
        (if any). Mutates entries in-place via dataclass replace."""
        updates: dict[str, Entry] = {}
        for nid, entry in self._index.items():
            if entry.parent_plugin_root is None:
                continue
            parent_entry = self._by_plugin_root.get(entry.parent_plugin_root.resolve())
            if parent_entry is None:
                continue
            updates[nid] = dataclasses.replace(entry, implicit_parent_nid=parent_entry.nid)
        self._index.update(updates)
        for entry in updates.values():
            if entry.plugin_root is not None:
                self._by_plugin_root[entry.plugin_root.resolve()] = entry

    # ---- public API ------------------------------------------------------------

    def qualified(self, entry) -> str:
        """`<namespace>-<stem>`: how a module is named across trees. A stem is
        unique inside its tree only; the root namespace is written `root`."""
        return f"{entry.namespace or 'root'}-{entry.path.stem}"

    def matches(self, key) -> list:
        """The entries `key` names, best kind of match only: nid, then name,
        stem or filename (a stem may live in several trees), then the qualified
        `<namespace>-<stem>`. Case-insensitive."""
        entry = self._index.get(key)
        if entry:
            return [entry]
        low = str(key).lower()
        entries = list(self._index.values())
        for test in (lambda e: e.nid.lower() == low,
                     lambda e: low in ((e.name or "").lower(), e.path.stem.lower(), e.path.name.lower()),
                     lambda e: self.qualified(e).lower() == low):
            found = [e for e in entries if test(e)]
            if found:
                return found
        return []

    def suggest(self, key) -> list:
        """Entries whose stem, name or qualified name contains `key` - what to
        offer when nothing matches."""
        low = str(key).lower()
        return sorted((e for e in self._index.values()
                       if low and (low in self.qualified(e).lower() or low in (e.name or "").lower())),
                      key=lambda e: self.qualified(e))

    def resolve(self, key):
        """Resolve a path, nid, name, stem, filename or `<namespace>-<stem>` to
        a Path; None when nothing matches.

        Priority: existing filesystem path > nid > name, stem or filename >
        qualified name. Matching is case-insensitive. A stem that lives in more
        than one tree raises `AmbiguousModule`: name it `<namespace>-<stem>`.
        """
        p = Path(key)
        if p.exists():
            return p
        found = self.matches(key)
        if len(found) > 1:
            raise exceptions.AmbiguousModule(str(key), sorted(self.qualified(e) for e in found))
        return found[0].path if found else None

    def all_targets(self, exclude_nid=None):
        """Return sorted list of all indexed paths."""
        return sorted(
            e.path for e in self._index.values()
            if not exclude_nid or e.nid != exclude_nid
        )

    def entries(self):
        """Snapshot of all entries, in insertion order."""
        return list(self._index.values())

    @property
    def roots(self):
        """The registry roots this index was built from, resolved, in order."""
        return self._roots

    def namespaces(self) -> list[Namespace]:
        """The declarations read in the pre-pass, in root order."""
        return [self._namespaces[r] for r in self._roots if r in self._namespaces]

    def namespace_for(self, nid) -> str | None:
        """The token of the tree that holds the module `nid`: "" in the root
        namespace, None in a legacy root or when this index does not hold it."""
        entry = self._index.get(nid)
        return None if entry is None else entry.namespace

    def qualified_for(self, nid) -> str | None:
        """`<namespace>-<stem>` of the module `nid`; None when this index does
        not hold it. The one name `resolve` always takes back to that module."""
        entry = self._index.get(nid)
        return None if entry is None else self.qualified(entry)

    def namespace_of(self, root) -> Namespace | None:
        """The declaration of `root`, or None (legacy root, or none written yet)."""
        return self._namespaces.get(Path(root).resolve())

    def extra_deps(self, nid):
        """Implicit-parent dependency lookup, suitable as `NfxTree(..., extra_deps=)`.

        Returns the entry's `implicit_parent_nid` wrapped in a list, or an
        empty list if absent / not in the index.
        """
        entry = self._index.get(nid)
        if entry and entry.implicit_parent_nid:
            return [entry.implicit_parent_nid]
        return []

    @property
    def metaontology_path(self):
        """Path of the discovered metaontology entry, or `None` if this view
        holds none."""
        for entry in self._index.values():
            if entry.type == "metaontology":
                return entry.path
        return None

    def tree(self, path) -> nfx.NfxTree:
        """The dependency DAG of the document at `path`, every pin resolved
        through this index whatever the type of the module it names. Raises
        `NfxCycle`. The one walk behind `closure`, `dependency_node_nids` and
        the redundant-pin check, so they cannot disagree about what a document
        depends on."""
        def _resolve(nid):
            e = self._index.get(nid)
            return nfx.read(e.path) if e else None
        return nfx.NfxTree(nfx.read(path), _resolve, extra_deps=self.extra_deps)

    def closure(self, path, include_self=False) -> list[Path]:
        """What has to be loaded for the document at `path`: the paths of its
        dependency closure, dependencies before dependants, the metaontology
        first (pinned or not).

        Type-blind - a knowledge module pinning a knowledge module pulls in
        that module and the ontologies behind it - so ask an `NfxIndex` unless
        the closure is known to stay inside one kind. The document itself is
        left out unless `include_self`. A pin on a module this index does not
        hold raises `NfxViolation`: a silent skip there loads half a closure
        and reports the rest as undefined types.
        """
        path = Path(path)
        tree = self.tree(path)
        if tree.missing:
            raise exceptions.NfxViolation(
                f"{path.stem}: dependency not in scope: {', '.join(sorted(tree.missing))}"
            )
        root_nid = tree.root.nid
        meta = next((e for e in self._index.values() if e.type == "metaontology"), None)
        paths = [] if meta is None else [meta.path]
        for nid in tree.topo_order():
            if nid != root_nid and (meta is None or nid != meta.nid):
                paths.append(self._index[nid].path)
        if include_self and (meta is None or root_nid != meta.nid):
            paths.append(path)
        return paths

    def dependency_node_nids(self, path) -> set[str]:
        """Every node nid declared by the modules the document at `path`
        depends on - what an import must treat as owned elsewhere."""
        return self.tree(path).all_node_nids(scope="dependencies")

    def dependency_nodes(self, path) -> dict:
        """The same nodes, each with what its declaring modules say of it -
        what lets an import tell a re-declared endpoint from an extension."""
        return self.tree(path).dependency_nodes()

    def check_dependency_versions(self, path):
        """Check that all dependencies have exact version match and that no
        direct dependency is also reachable transitively. Returns list of
        error strings."""
        doc = nfx.read(path)
        errors = []
        for dep_nid, required_version in doc.dependencies:
            entry = self._index.get(dep_nid)
            if not entry:
                errors.append(f"dependency {dep_nid} not found in index")
                continue
            if entry.version != required_version:
                dep_name = entry.name or entry.path.stem
                errors.append(f"{dep_name} requires {required_version}, found {entry.version}")

        try:
            tree = self.tree(path)
        except exceptions.NfxCycle:
            return errors
        for nid in tree.redundant_directs():
            e = self._index.get(nid)
            name = e.name or e.path.stem if e else nid.split("-", 1)[0]
            errors.append(f"{name} is both a direct and a transitive dependency - drop the direct pin")
        return errors


class NfxIndex(PluginIndex):
    """Type-agnostic view: registers every `.nfx` reachable from the roots."""

    KIND = ()


class OntologyIndex(PluginIndex):
    """Ontology view: registers `.nfx` whose `type` is `ontology` or
    `metaontology`. The metaontology is discovered through the standard scan
    (its directory must be one of the PLUGINS roots, which is the default)."""

    KIND = ("ontology", "metaontology")


class KnowledgeIndex(PluginIndex):
    """Knowledge view: registers `.nfx` whose `type == "knowledge"`."""

    KIND = ("knowledge",)
