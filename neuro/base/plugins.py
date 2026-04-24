"""
Plugin system for ontology-declared type validators.

The sibling `validators.py` registers Python validators for OntologyProperty
subclasses declared in the .nfx, via the `@validator` decorator.

Validator signature: `fn(value, metaproperty) -> bool`. `metaproperty` is
the `neuro.base.schema.Metaproperty` being validated; most validators can
ignore it, but types whose check depends on context (e.g. `Label` switching
on the owning class kind via `metaproperty.deep_node`) need it.

    from neuro.base.plugins import validator

    @validator("Posint")
    def _(v, _mp):
        return isinstance(v, int) and not isinstance(v, bool) and v > 0

Loading is driven by `OntologyIndex._scan` — every discovered `.nfx` in
dir-form has its sibling `validators.py` imported exactly once.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Callable, TypeAlias


Validator: TypeAlias = Callable[[object, object], bool]

_VALIDATORS_FILENAME = "validators.py"
_PLUGIN_MODULE_PREFIX = "neuro._ontology_plugins"


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


def plugin_dir_for(nfx_path: Path | str) -> Path | None:
    """Return the plugin directory for an nfx path, or None if flat-form.

    Dir form: `<parent>/<stem>/<stem>.nfx` — the nfx stem matches its dir name.
    """
    path = Path(nfx_path)
    return path.parent if path.parent.name == path.stem else None


def load_plugin_at(nfx_path: Path | str) -> bool:
    """Import the sibling `validators.py` for a dir-form nfx.

    Returns True on successful load (or if already loaded), False when the nfx
    is flat-form or the dir has no validators.py.
    """
    plugin_dir = plugin_dir_for(nfx_path)
    if plugin_dir is None:
        return False
    validators_path = plugin_dir / _VALIDATORS_FILENAME
    if not validators_path.is_file():
        return False
    return _import_file_as_module(
        f"{_PLUGIN_MODULE_PREFIX}.{plugin_dir.name}",
        validators_path,
    )


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
