"""
Ontology file discovery and indexing.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from neuro.base import nfx, plugins
from neuro.utils import exceptions, internal_utils


@dataclass(frozen=True)
class Entry:
    path: Path
    nid: str
    name: str
    version: str


class OntologyIndex:
    """Index of .nfx ontology files discovered from directory search paths.

    Keyed canonically by `nid`. `resolve()` additionally accepts name, stem,
    or filename via priority-ordered fallback. Pure file-level discovery —
    no database access.
    """

    def __init__(self, *dirs):
        self._index: dict[str, Entry] = {}
        self._metaontology_path = (
            internal_utils.get_path("assets") / "ontology" / "metaontology.nfx"
        )
        self._scan(dirs)

    def _register(self, path):
        doc = nfx.read(path)
        if not doc.nid:
            return
        existing = self._index.get(doc.nid)
        if existing and existing.path != path:
            raise exceptions.NfxViolation(
                f"nid collision: {doc.nid} claimed by {existing.path} and {path}"
            )
        self._index[doc.nid] = Entry(
            path=path,
            nid=doc.nid,
            name=doc.name,
            version=doc.version,
        )

    def _scan(self, dirs):
        # Pin metaontology first so a stray copy in a search dir can't shadow it.
        self._register(self._metaontology_path)
        plugins.load_plugin_at(self._metaontology_path)
        for d in dirs:
            for root, _, files in os.walk(d, followlinks=True):
                for fname in files:
                    if not fname.endswith(".nfx"):
                        continue
                    path = Path(root) / fname
                    if path != self._metaontology_path:
                        self._register(path)
                    plugins.load_plugin_at(path)

    def resolve(self, key):
        """Resolve a path, nid, name, stem, or filename to a Path.

        Priority: existing filesystem path > nid > name > stem > filename.
        """
        p = Path(key)
        if p.exists():
            return p
        entry = self._index.get(key)
        if entry:
            return entry.path
        entries = list(self._index.values())
        for e in entries:
            if e.name == key:
                return e.path
        for e in entries:
            if e.path.stem == key:
                return e.path
        for e in entries:
            if e.path.name == key:
                return e.path
        return None

    def all_targets(self, exclude_nid=None):
        """Return sorted list of all indexed ontology paths."""
        return sorted(
            e.path for e in self._index.values()
            if not exclude_nid or e.nid != exclude_nid
        )

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
            tree = nfx.NfxTree(doc, _resolve)
        except exceptions.NfxCycle:
            return errors
        for nid in tree.redundant_directs():
            e = self._index.get(nid)
            name = e.name or e.path.stem if e else nid.split("-", 1)[0]
            errors.append(f"{name} is both a direct and a transitive dependency — drop the direct pin")
        return errors

    @property
    def metaontology_path(self):
        return self._metaontology_path
