"""
Ontology file discovery and indexing.
"""

import os
from pathlib import Path

from neuro.base import nfx
from neuro.utils import internal_utils


class OntologyIndex:
    """Index of .nfx ontology files discovered from directory search paths.

    Pure file-level discovery — no database access.
    """

    def __init__(self, *dirs):
        self._index = {}
        self._metaontology_path = internal_utils.get_path("assets") / "ontology" / "metaontology.nfx"
        self._scan(dirs)

    def _scan(self, dirs):
        # Pin metaontology to the canonical path.
        data = nfx.read(self._metaontology_path)
        for key in (data.get("nid", ""), data.get("name", ""), self._metaontology_path.stem, self._metaontology_path.name):
            if key:
                self._index[key] = self._metaontology_path
        for d in dirs:
            for root, _, files in os.walk(d, followlinks=True):
                for fname in files:
                    if not fname.endswith(".nfx"):
                        continue
                    path = Path(root) / fname
                    data = nfx.read(path)
                    nid = data.get("nid", "")
                    if nid:
                        self._index.setdefault(nid, path)
                    name = data.get("name", "")
                    if name:
                        self._index.setdefault(name, path)
                    self._index.setdefault(path.stem, path)
                    self._index.setdefault(path.name, path)

    def resolve(self, key):
        """Resolve a name, nid, stem, filename, or file path to a Path."""
        p = Path(key)
        if p.exists():
            return p
        return self._index.get(key)

    def all_targets(self, exclude_nid=None):
        """Return deduplicated, sorted list of all indexed ontology paths."""
        targets = sorted(
            p for p in self._index.values()
            if not exclude_nid or nfx.read(p).get("nid") != exclude_nid
        )
        seen = set()
        return [p for p in targets if str(p) not in seen and not seen.add(str(p))]

    def check_dependency_versions(self, path):
        """Check that all dependencies have exact version match. Returns list of error strings."""
        data = nfx.read(path)
        errors = []
        for dep in data.get("dependencies", []):
            dep_nid, _, required_version = dep.partition("@")
            dep_path = self._index.get(dep_nid)
            if not dep_path:
                errors.append(f"dependency {dep_nid} not found in index")
                continue
            if not required_version:
                continue
            dep_data = nfx.read(dep_path)
            actual_version = dep_data.get("version", "")
            if actual_version != required_version:
                dep_name = dep_data.get("name", dep_path.stem)
                errors.append(f"{dep_name} requires {required_version}, found {actual_version}")
        return errors

    @property
    def metaontology_path(self):
        return self._metaontology_path
