"""
Plugin file discovery and indexing.

`PluginIndex` is the generic base; subclasses set a `KIND` tuple to restrict
the view to one or more `type` values from the on-disk `.nfx`. With `KIND = ()`
the index accepts every type — `NfxIndex` is that unrestricted view.
`OntologyIndex` accepts ontology + metaontology; `KnowledgeIndex` accepts
knowledge.

Discovery is delegated to `neuro.base.plugins.walk_plugins`. Validators are
loaded once per plugin root via `plugins.load_validators_at`. Implicit parent
dependencies (nested-plugin "ontology import" semantics) are computed at
register time and surfaced via `Entry.implicit_parent_nid`; `_topo` /
`NfxTree` callers obtain them through the index's `extra_deps` callable.
"""

from dataclasses import dataclass
from pathlib import Path

from neuro.base import nfx, plugins
from neuro.utils import exceptions


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


class PluginIndex:
    """Index of `.nfx` files discovered from PLUGINS registry roots, filtered
    by the subclass's `KIND` tuple (empty = accept all types).

    Keyed canonically by `nid`. `resolve()` additionally accepts name, stem,
    or filename via priority-ordered fallback. Pure file-level discovery —
    no database access.
    """

    KIND: tuple[str, ...] = ()

    def __init__(self, *roots):
        self._index: dict[str, Entry] = {}
        self._by_plugin_root: dict[Path, Entry] = {}
        self._roots = tuple(Path(r).resolve() for r in roots)
        self._scan()
        self._resolve_implicit_parents()

    # ---- registration ----------------------------------------------------------

    def _register(
        self,
        path: Path,
        plugin_root: Path | None = None,
        parent_plugin_root: Path | None = None,
    ) -> Entry | None:
        doc = nfx.read(path)
        if not doc.nid:
            return None
        if self.KIND and doc.type not in self.KIND:
            return None
        existing = self._index.get(doc.nid)
        if existing and existing.path != path:
            raise exceptions.NfxViolation(
                f"nid collision: {doc.nid} claimed by {existing.path} and {path}"
            )
        entry = Entry(
            path=path,
            nid=doc.nid,
            type=doc.type,
            name=doc.name,
            version=doc.version,
            plugin_root=plugin_root,
            parent_plugin_root=parent_plugin_root,
        )
        self._index[doc.nid] = entry
        if plugin_root is not None:
            self._by_plugin_root[plugin_root.resolve()] = entry
        return entry

    def _scan(self) -> None:
        for pf in plugins.walk_plugins(self._roots):
            self._register(pf.nfx_path, pf.plugin_root, pf.parent_plugin_root)
            plugins.load_validators_at(pf.plugin_root)

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
            updates[nid] = Entry(
                path=entry.path,
                nid=entry.nid,
                type=entry.type,
                name=entry.name,
                version=entry.version,
                plugin_root=entry.plugin_root,
                parent_plugin_root=entry.parent_plugin_root,
                implicit_parent_nid=parent_entry.nid,
            )
        self._index.update(updates)
        for entry in updates.values():
            if entry.plugin_root is not None:
                self._by_plugin_root[entry.plugin_root.resolve()] = entry

    # ---- public API ------------------------------------------------------------

    def resolve(self, key):
        """Resolve a path, nid, name, stem, or filename to a Path.

        Priority: existing filesystem path > nid > name > stem > filename.
        Nid/name/stem/filename matching is case-insensitive.
        """
        p = Path(key)
        if p.exists():
            return p
        entry = self._index.get(key)
        if entry:
            return entry.path
        key_lower = key.lower()
        entries = list(self._index.values())
        for e in entries:
            if e.nid.lower() == key_lower:
                return e.path
        for e in entries:
            if (e.name or "").lower() == key_lower:
                return e.path
        for e in entries:
            if e.path.stem.lower() == key_lower:
                return e.path
        for e in entries:
            if e.path.name.lower() == key_lower:
                return e.path
        return None

    def all_targets(self, exclude_nid=None):
        """Return sorted list of all indexed paths."""
        return sorted(
            e.path for e in self._index.values()
            if not exclude_nid or e.nid != exclude_nid
        )

    def entries(self):
        """Snapshot of all entries, in insertion order."""
        return list(self._index.values())

    def extra_deps(self, nid):
        """Implicit-parent dependency lookup, suitable as `NfxTree(..., extra_deps=)`.

        Returns the entry's `implicit_parent_nid` wrapped in a list, or an
        empty list if absent / not in the index.
        """
        entry = self._index.get(nid)
        if entry and entry.implicit_parent_nid:
            return [entry.implicit_parent_nid]
        return []

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

        def _resolve(nid):
            e = self._index.get(nid)
            return nfx.read(e.path) if e else None
        try:
            tree = nfx.NfxTree(doc, _resolve, extra_deps=self.extra_deps)
        except exceptions.NfxCycle:
            return errors
        for nid in tree.redundant_directs():
            e = self._index.get(nid)
            name = e.name or e.path.stem if e else nid.split("-", 1)[0]
            errors.append(f"{name} is both a direct and a transitive dependency — drop the direct pin")
        return errors


class NfxIndex(PluginIndex):
    """Type-agnostic view: registers every `.nfx` reachable from the roots."""

    KIND = ()


class OntologyIndex(PluginIndex):
    """Ontology view: registers `.nfx` whose `type` is `ontology` or
    `metaontology`. The metaontology is discovered through the standard scan
    (its directory must be one of the PLUGINS roots, which is the default)."""

    KIND = ("ontology", "metaontology")

    @property
    def metaontology_path(self):
        """Path of the discovered metaontology entry, or `None` if absent."""
        for entry in self._index.values():
            if entry.type == "metaontology":
                return entry.path
        return None


class KnowledgeIndex(PluginIndex):
    """Knowledge view: registers `.nfx` whose `type == "knowledge"`."""

    KIND = ("knowledge",)
