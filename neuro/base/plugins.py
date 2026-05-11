"""
Plugin system: validator registry and on-disk plugin discovery.

A *plugin* is a directory under a PLUGINS registry root that owns one or more
`.nfx` files. Three valid layouts are recognised:

- Bare:        `<root>/<name>.nfx`                       (no validators possible)
- Flat-dir:    `<root>/<name>/<name>.nfx`                (validators at `<root>/<name>/validators.py`)
- Kind-subdir: `<root>/<name>/{ontology,knowledge}/...`  (validators at `<root>/<name>/validators.py`)

Sub-plugins nest by directory: `<root>/<parent>/<child>/...` makes `<child>` a
sub-plugin of `<parent>` (recognised when both dirs themselves own an `.nfx`).

Plugins carry no manifest; classification of `.nfx` files into ontology /
knowledge / metaontology is read from each file's own `type` field, not from
its enclosing directory name. Per-file versioning is unchanged.

The sibling `validators.py` registers Python validators for OntologyProperty
subclasses declared in the `.nfx`, via the `@validator` decorator.

Validator signature: `fn(value, metaproperty) -> bool`. `metaproperty` is
the `neuro.base.schema.Metaproperty` being validated; most validators can
ignore it, but types whose check depends on context (e.g. `Label` switching
on the owning class kind via `metaproperty.deep_node`) need it.

    from neuro.base.plugins import validator

    @validator("Posint")
    def _(v, _mp):
        return isinstance(v, int) and not isinstance(v, bool) and v > 0

Loading is driven by `PluginIndex._scan` — every discovered plugin root has
its `validators.py` imported exactly once.
"""

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, TypeAlias


Validator: TypeAlias = Callable[[object, object], bool]

_VALIDATORS_FILENAME = "validators.py"
_PLUGIN_MODULE_PREFIX = "neuro._plugins"
_KIND_SUBDIRS = ("ontology", "knowledge")
_SUBPLUGIN_CONTAINER = "plugins"
_RESERVED_DIR_NAMES = (*_KIND_SUBDIRS, _SUBPLUGIN_CONTAINER)


class ValidatorRegistry:
    """Mapping from type labels to `(value, metaproperty) -> bool` predicates."""

    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}

    def register(self, label: str, fn: Validator) -> None:
        self._validators[label] = fn

    def validator(self, label: str) -> Callable[[Validator], Validator]:
        """Decorator form of `register`."""
        def decorate(fn: Validator) -> Validator:
            self.register(label, fn)
            return fn
        return decorate

    def lookup(self, label: str) -> Validator | None:
        return self._validators.get(label)

    def labels(self) -> list[str]:
        """Snapshot of registered labels, sorted."""
        return sorted(self._validators)

    def clear(self) -> None:
        self._validators.clear()


_registry = ValidatorRegistry()

register = _registry.register
validator = _registry.validator
lookup = _registry.lookup
registered_labels = _registry.labels
clear = _registry.clear


@dataclass(frozen=True)
class PluginFile:
    """One discovered `.nfx` and its enclosing plugin context.

    `plugin_root` is None for a bare nfx sitting directly under a registry root
    (no validators possible). `parent_plugin_root` is None when the plugin has
    no enclosing parent plugin (top-level under a registry root).
    """
    nfx_path: Path
    registry_root: Path
    plugin_root: Path | None
    parent_plugin_root: Path | None


def _normalise_roots(registry_roots: Iterable[Path | str]) -> tuple[Path, ...]:
    return tuple(Path(r).resolve() for r in registry_roots)


def plugin_root_for(
    nfx_path: Path | str,
    registry_roots: Iterable[Path | str] = (),
) -> Path | None:
    """Return the plugin directory owning `nfx_path`, or None for a bare nfx.

    Rules (with `registry_roots` provided):
      - If `nfx_path.parent` is itself a registry root → None (bare).
      - If `nfx_path.parent.name` is "plugins" (sub-plugin container) → None
        (bare sub-plugin; parent linkage handled by `walk_plugins`).
      - If `nfx_path.parent.name` is "ontology" or "knowledge" → return
        `nfx_path.parent.parent` (kind-subdir layout).
      - Otherwise → return `nfx_path.parent` (flat-dir or dir-form sub-plugin).

    With no `registry_roots`, falls back to the legacy heuristic
    (parent dir name equals nfx stem implies dir-form). Kept so older callers
    that have not yet been threaded with registry roots keep working.
    """
    path = Path(nfx_path).resolve()
    roots = _normalise_roots(registry_roots)
    if not roots:
        return path.parent if path.parent.name == path.stem else None
    parent = path.parent
    if parent in roots:
        return None
    if parent.name == _SUBPLUGIN_CONTAINER:
        return None
    if parent.name in _KIND_SUBDIRS:
        return parent.parent
    return parent


def _owns_nfx(directory: Path) -> bool:
    """True if `directory` directly contains any `.nfx`, or holds one inside
    its own `ontology/`/`knowledge/` subdir. Sub-plugin dirs are not consulted —
    those are themselves plugins, not files owned by `directory`."""
    if not directory.is_dir():
        return False
    for entry in directory.iterdir():
        if entry.is_file() and entry.suffix == ".nfx":
            return True
    for kind in _KIND_SUBDIRS:
        sub = directory / kind
        if sub.is_dir() and any(p.suffix == ".nfx" for p in sub.iterdir() if p.is_file()):
            return True
    return False


def _enclosing_plugin(
    start: Path,
    roots: tuple[Path, ...],
) -> Path | None:
    """Walk up from `start.parent` and return the first ancestor that owns
    its own `.nfx` (flat or via a kind subdir). Reserved container names
    (`plugins/`, `ontology/`, `knowledge/`) are skipped — they may carry
    files but are never themselves treated as plugins. Stops at any registry
    root or when leaving every registry root's subtree."""
    if not roots:
        return None
    ancestor = start.parent
    while True:
        if ancestor in roots:
            return None
        if not any(_is_under(ancestor, r) for r in roots):
            return None
        if ancestor.name not in _RESERVED_DIR_NAMES and _owns_nfx(ancestor):
            return ancestor
        if ancestor.parent == ancestor:
            return None
        ancestor = ancestor.parent


def parent_plugin_root(
    plugin_root: Path | str,
    registry_roots: Iterable[Path | str],
) -> Path | None:
    """Return the enclosing plugin's root, or None if `plugin_root` is top-level."""
    if not plugin_root:
        return None
    return _enclosing_plugin(
        Path(plugin_root).resolve(),
        _normalise_roots(registry_roots),
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def walk_plugins(registry_roots: Iterable[Path | str]) -> Iterator[PluginFile]:
    """Yield every `.nfx` under each registry root, with plugin context.

    Symlinks are followed (matching the prior `os.walk(..., followlinks=True)`).
    Order is `os.walk` order per root, then root order.
    """
    roots = _normalise_roots(registry_roots)
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
            dir_path = Path(dirpath)
            for fname in filenames:
                if not fname.endswith(".nfx"):
                    continue
                nfx_path = dir_path / fname
                proot = plugin_root_for(nfx_path, roots)
                # For bare nfx (no plugin_root), parent linkage is still
                # possible when nested inside a `plugins/` sub-plugin container.
                parent_start = proot if proot is not None else nfx_path
                parent = _enclosing_plugin(parent_start, roots)
                yield PluginFile(
                    nfx_path=nfx_path,
                    registry_root=root,
                    plugin_root=proot,
                    parent_plugin_root=parent,
                )


def load_validators_at(plugin_root: Path | str | None) -> bool:
    """Import `validators.py` at the given plugin root, if present.

    Returns True if loaded (or already in `sys.modules`), False otherwise.
    A `None` plugin_root (bare nfx) always returns False.
    """
    if plugin_root is None:
        return False
    plugin_root = Path(plugin_root)
    validators_path = plugin_root / _VALIDATORS_FILENAME
    if not validators_path.is_file():
        return False
    # Module name = absolute resolved path with separators turned into dots,
    # guaranteeing uniqueness across nested/shadowed plugin names and
    # idempotency when the same plugin_root is loaded twice.
    resolved = plugin_root.resolve()
    qualified = "_".join(part for part in resolved.parts if part not in ("", "/"))
    return _import_file_as_module(
        f"{_PLUGIN_MODULE_PREFIX}.{qualified}",
        validators_path,
    )


# Legacy compat — older callers pass an nfx path and expect dir-form detection
# via the `parent.name == stem` heuristic. Keep these until commit 3 migrates
# all callers to the registry-aware API.
def plugin_dir_for(nfx_path: Path | str) -> Path | None:
    """Legacy: return plugin dir using the `parent.name == stem` heuristic."""
    return plugin_root_for(nfx_path)


def load_plugin_at(nfx_path: Path | str) -> bool:
    """Legacy: import `validators.py` next to a dir-form `.nfx`."""
    return load_validators_at(plugin_dir_for(nfx_path))


def _import_file_as_module(module_name: str, path: Path) -> bool:
    """Import `path` as `module_name`; no-op if already in `sys.modules`."""
    if module_name in sys.modules:
        return True
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return False
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return True
