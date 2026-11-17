"""
Plugin system: validator registry and on-disk plugin discovery.

Two kinds of registry root exist.

**Consolidated root** - a directory named `.nf`, acting as a whole:

    <dir>/.nf/
      namespace.nfx            the root's namespace declaration
      ontology/<Name>.nfx      one module per file; local name = stem
      knowledge/<Name>.nfx
      validators/<name>.py     validators for ontology/<Name>.nfx; sha256 = its `hash`
      tests/                   not scanned

Only `ontology/`, `knowledge/` and the root's own `*.nfx` are read; nothing
nests. A file's kind subdir and its `type` field must agree, and a local name
may not repeat inside one root - both are enforced by `PluginIndex`.

**Legacy root** - any other directory. A *plugin* is a subdirectory that owns
one or more `.nfx` files, in one of three layouts, all transitional:

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

Loading is driven by `PluginIndex._scan` - every discovered validators file
(`PluginFile.validators_path`) is imported exactly once.
"""

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, TypeAlias

from neuro.utils import internal_utils


Validator: TypeAlias = Callable[[object, object], bool]

NF_DIRNAME = ".nf"
_VALIDATORS_FILENAME = "validators.py"
_VALIDATORS_DIR = "validators"
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
    and for every file of a consolidated root (no plugin directories there).
    `parent_plugin_root` is None when the plugin has no enclosing parent plugin
    (top-level under a registry root). `validators_path` is where this
    module's validators live if it has any - `<plugin>/validators.py` in a
    legacy root, `validators/<stem>.py` in a consolidated one - whether or not
    the file exists. `expected_type` is the `type` the file's kind subdir
    demands in a consolidated root (`ontology/` → "ontology", `knowledge/` →
    "knowledge"), None where the path says nothing.
    """
    nfx_path: Path
    registry_root: Path
    plugin_root: Path | None
    parent_plugin_root: Path | None
    validators_path: Path | None = None
    expected_type: str | None = None


def _normalise_roots(registry_roots: Iterable[Path | str]) -> tuple[Path, ...]:
    return tuple(Path(r).resolve() for r in registry_roots)


def is_consolidated(root: Path | str) -> bool:
    """True for a `.nf` root - the consolidated layout."""
    return Path(root).name == NF_DIRNAME


def effective_roots() -> list[Path]:
    """The PLUGINS roots in effect for this process, missing entries skipped.

    The one way callers obtain the registry roots: the
    colon-separated `PLUGINS` of the current environment, each entry resolved
    against `APP_DIR`, an absent one logged and dropped rather than fatal, so a
    machine without every root checked out still builds.
    """
    return internal_utils.get_path_list("PLUGINS")


def registry_root_of(path: Path | str, registry_roots: Iterable[Path | str]) -> Path | None:
    """The registry root `path` sits under, or None if it is outside all of them."""
    resolved = Path(path).resolve()
    for root in _normalise_roots(registry_roots):
        if _is_under(resolved, root):
            return root
    return None


def validators_path_for(
    nfx_path: Path | str,
    registry_roots: Iterable[Path | str],
) -> Path | None:
    """Where the validators for `nfx_path` live, in either kind of root.

    Consolidated root: `<root>/validators/<stem>.py` for a file under
    `ontology/` or `knowledge/`; None for the root's own files
    (`namespace.nfx`). Legacy root: `<plugin>/validators.py`, None for a bare
    nfx. The returned path need not exist - this is the *rule*, used by the
    hash check and `ontology.rehash` alike.
    """
    path = Path(nfx_path).resolve()
    roots = _normalise_roots(registry_roots)
    root = registry_root_of(path, roots)
    if root is not None and is_consolidated(root):
        if path.parent.parent == root and path.parent.name in _KIND_SUBDIRS:
            return root / _VALIDATORS_DIR / f"{path.stem}.py"
        return None
    proot = plugin_root_for(path, roots)
    return None if proot is None else proot / _VALIDATORS_FILENAME


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
    its own `ontology/`/`knowledge/` subdir. Sub-plugin dirs are not consulted -
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
    (`plugins/`, `ontology/`, `knowledge/`) are skipped - they may carry
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


def _nfx_files(directory: Path) -> list[Path]:
    """The `.nfx` files directly inside `directory`, sorted; [] if it is not a dir."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".nfx")


def _walk_consolidated(root: Path) -> Iterator[PluginFile]:
    """Yield the files of a `.nf` root: its own `*.nfx` (the namespace
    declaration), then `ontology/*.nfx` and `knowledge/*.nfx`. Nothing else in
    the root is looked at - `validators/`, `tests/`, `tw5-editions/` and any
    stray directory are not module containers."""
    for nfx_path in _nfx_files(root):
        yield PluginFile(nfx_path=nfx_path, registry_root=root, plugin_root=None, parent_plugin_root=None)
    for kind in _KIND_SUBDIRS:
        for nfx_path in _nfx_files(root / kind):
            yield PluginFile(
                nfx_path=nfx_path,
                registry_root=root,
                plugin_root=None,
                parent_plugin_root=None,
                validators_path=root / _VALIDATORS_DIR / f"{nfx_path.stem}.py",
                expected_type=kind,
            )


def _walk_legacy(root: Path, roots: tuple[Path, ...]) -> Iterator[PluginFile]:
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
                validators_path=None if proot is None else proot / _VALIDATORS_FILENAME,
            )


def walk_plugins(registry_roots: Iterable[Path | str]) -> Iterator[PluginFile]:
    """Yield every `.nfx` under each registry root, with plugin context.

    A `.nf` root is read by the consolidated rule (`_walk_consolidated`); any
    other root by the legacy layouts, symlinks followed, in `os.walk` order.
    Roots come in the order given; a root that is not a directory is skipped.
    """
    roots = _normalise_roots(registry_roots)
    for root in roots:
        if not root.is_dir():
            continue
        if is_consolidated(root):
            yield from _walk_consolidated(root)
        else:
            yield from _walk_legacy(root, roots)


def load_validators_file(validators_path: Path | str | None) -> bool:
    """Import a validators module by path, if the file exists.

    Returns True if loaded (or already in `sys.modules`), False otherwise.
    """
    if validators_path is None:
        return False
    validators_path = Path(validators_path)
    if not validators_path.is_file():
        return False
    # Module name = absolute resolved path with separators turned into dots,
    # guaranteeing uniqueness across nested/shadowed plugin names and
    # idempotency when the same file is loaded twice.
    resolved = validators_path.resolve()
    qualified = "_".join(part for part in resolved.with_suffix("").parts if part not in ("", "/"))
    return _import_file_as_module(f"{_PLUGIN_MODULE_PREFIX}.{qualified}", validators_path)


def load_validators(plugin_file: PluginFile) -> bool:
    """Import the validators a discovered file points at, if any."""
    return load_validators_file(plugin_file.validators_path)


def load_validators_at(plugin_root: Path | str | None) -> bool:
    """Import `validators.py` at the given legacy plugin root, if present.

    A `None` plugin_root (bare nfx) always returns False.
    """
    if plugin_root is None:
        return False
    return load_validators_file(Path(plugin_root) / _VALIDATORS_FILENAME)


# Legacy compat - older callers pass an nfx path and expect dir-form detection
# via the `parent.name == stem` heuristic. Not for the hash path any more:
# `validators_path_for` knows both kinds of root.
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
