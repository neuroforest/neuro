"""
Unit tests for neuro.base.plugins — validator registry and plugin loading.
"""

import sys
import textwrap

import pytest

from neuro.base import plugins
from neuro.base.schema import Metaproperty

pytestmark = pytest.mark.unit


def _reset_registry():
    plugins.clear()
    for name in list(sys.modules):
        if name.startswith("neuro._ontology_plugins."):
            del sys.modules[name]


@pytest.fixture(autouse=True)
def clean_registry():
    _reset_registry()
    yield
    _reset_registry()


def _make_metaproperty(property_type):
    return Metaproperty({
        "property": "x",
        "node": "Test",
        "node_object": None,
        "property_object": None,
        "property_type": property_type,
        "relationship_type": "HAS_PROPERTY",
        "deep_node": "OntologyNode",
    })


class TestRegistry:
    def test_register_and_lookup(self):
        plugins.register("Posint", lambda v, _mp: isinstance(v, int) and v > 0)
        fn = plugins.lookup("Posint")
        assert fn(5, None) is True
        assert fn(0, None) is False

    def test_lookup_missing(self):
        assert plugins.lookup("Nonexistent") is None

    def test_decorator(self):
        @plugins.validator("Even")
        def _(v, _mp):
            return isinstance(v, int) and v % 2 == 0
        assert plugins.lookup("Even")(4, None) is True
        assert plugins.lookup("Even")(3, None) is False

    def test_registered_labels(self):
        plugins.register("A", lambda v, _mp: True)
        plugins.register("B", lambda v, _mp: True)
        assert plugins.registered_labels() == ["A", "B"]


class TestPluginDirFor:
    def test_dir_form(self, tmp_path):
        (tmp_path / "math").mkdir()
        nfx_path = tmp_path / "math" / "math.nfx"
        nfx_path.touch()
        assert plugins.plugin_dir_for(nfx_path) == tmp_path / "math"

    def test_flat_form(self, tmp_path):
        nfx_path = tmp_path / "ncbi.nfx"
        nfx_path.touch()
        assert plugins.plugin_dir_for(nfx_path) is None


class TestLoadPluginAt:
    def _write_plugin(self, tmp_path, name, body):
        pkg = tmp_path / name
        pkg.mkdir()
        (pkg / f"{name}.nfx").touch()
        (pkg / "validators.py").write_text(textwrap.dedent(body))
        return pkg / f"{name}.nfx"

    def test_loads_dir_form(self, tmp_path):
        nfx_path = self._write_plugin(tmp_path, "math", """
            from neuro.base.plugins import validator

            @validator("Posint")
            def _(v, _mp):
                return isinstance(v, int) and not isinstance(v, bool) and v > 0
        """)
        assert plugins.load_plugin_at(nfx_path) is True
        assert plugins.lookup("Posint")(42, None) is True
        assert plugins.lookup("Posint")(-1, None) is False

    def test_flat_form_returns_false(self, tmp_path):
        nfx_path = tmp_path / "ncbi.nfx"
        nfx_path.touch()
        assert plugins.load_plugin_at(nfx_path) is False

    def test_dir_form_without_validators(self, tmp_path):
        (tmp_path / "bare").mkdir()
        nfx_path = tmp_path / "bare" / "bare.nfx"
        nfx_path.touch()
        assert plugins.load_plugin_at(nfx_path) is False

    def test_idempotent(self, tmp_path):
        nfx_path = self._write_plugin(tmp_path, "counted", """
            import itertools
            from neuro.base.plugins import register

            _counter = itertools.count()
            register("Counted", lambda v, _mp: next(_counter) == 0)
        """)
        plugins.load_plugin_at(nfx_path)
        plugins.load_plugin_at(nfx_path)   # second call must not re-exec
        assert plugins.lookup("Counted")(None, None) is True


class TestMetapropertyUsesRegistry:
    def test_registered_type_validates(self):
        plugins.register("Posint", lambda v, _mp: isinstance(v, int) and not isinstance(v, bool) and v > 0)
        mp = _make_metaproperty("Posint")
        assert mp.validate(620) is True
        assert mp.validate(0) is False
        assert mp.validate(-1) is False
        assert mp.validate("620") is False

    def test_unregistered_type_fails_closed(self):
        mp = _make_metaproperty("Nonexistent")
        assert mp.validate("anything") is False

    def test_validator_receives_metaproperty(self):
        captured = {}
        plugins.register("Capture", lambda v, mp: captured.setdefault("mp", mp) or True)
        mp = _make_metaproperty("Capture")
        mp.validate("x")
        assert captured["mp"] is mp
