"""
Unit tests for neuro.base.plugins - validator registry and plugin loading.
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
        if name.startswith("neuro._plugins."):
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
        "relationship_lineage": ["HAS_PROPERTY"],
        "deep_node": "OntologyNode",
        "distance": 0,
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


class TestPluginRootFor:
    def test_bare(self, tmp_path):
        nfx_path = tmp_path / "a.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) is None

    def test_flat_dir(self, tmp_path):
        (tmp_path / "p").mkdir()
        nfx_path = tmp_path / "p" / "p.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) == (tmp_path / "p").resolve()

    def test_kind_subdir_ontology(self, tmp_path):
        (tmp_path / "p" / "ontology").mkdir(parents=True)
        nfx_path = tmp_path / "p" / "ontology" / "p.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) == (tmp_path / "p").resolve()

    def test_kind_subdir_knowledge(self, tmp_path):
        (tmp_path / "p" / "knowledge").mkdir(parents=True)
        nfx_path = tmp_path / "p" / "knowledge" / "p.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) == (tmp_path / "p").resolve()

    def test_sub_plugin_flat(self, tmp_path):
        (tmp_path / "parent" / "child").mkdir(parents=True)
        nfx_path = tmp_path / "parent" / "child" / "child.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) == (tmp_path / "parent" / "child").resolve()

    def test_bare_nfx_inside_plugins_container(self, tmp_path):
        (tmp_path / "parent" / "plugins").mkdir(parents=True)
        nfx_path = tmp_path / "parent" / "plugins" / "child.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) is None

    def test_dir_form_inside_plugins_container(self, tmp_path):
        (tmp_path / "parent" / "plugins" / "child").mkdir(parents=True)
        nfx_path = tmp_path / "parent" / "plugins" / "child" / "child.nfx"
        nfx_path.touch()
        assert plugins.plugin_root_for(nfx_path, [tmp_path]) == (
            tmp_path / "parent" / "plugins" / "child"
        ).resolve()


class TestParentPluginRoot:
    def test_top_level_returns_none(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / "parent.nfx").touch()
        assert plugins.parent_plugin_root(parent, [tmp_path]) is None

    def test_nested_returns_parent(self, tmp_path):
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / "parent.nfx").touch()
        (child / "child.nfx").touch()
        assert plugins.parent_plugin_root(child, [tmp_path]) == parent.resolve()

    def test_intermediate_without_nfx_walks_through(self, tmp_path):
        parent = tmp_path / "parent"
        child = parent / "mid" / "child"
        child.mkdir(parents=True)
        (parent / "parent.nfx").touch()
        (child / "child.nfx").touch()
        # `mid/` owns no nfx → parent_plugin is `parent`.
        assert plugins.parent_plugin_root(child, [tmp_path]) == parent.resolve()

    def test_parent_owns_only_kind_subdir_nfx(self, tmp_path):
        parent = tmp_path / "parent"
        parent_ont = parent / "ontology"
        child = parent / "child"
        parent_ont.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent_ont / "parent.nfx").touch()
        (child / "child.nfx").touch()
        assert plugins.parent_plugin_root(child, [tmp_path]) == parent.resolve()

    def test_skips_plugins_container(self, tmp_path):
        parent = tmp_path / "parent"
        child = parent / "plugins" / "child"
        child.mkdir(parents=True)
        (parent / "parent.nfx").touch()
        (child / "child.nfx").touch()
        # The `plugins/` container is reserved and skipped during the walk.
        assert plugins.parent_plugin_root(child, [tmp_path]) == parent.resolve()


class TestWalkPlugins:
    def test_yields_bare_and_dir_form(self, tmp_path):
        (tmp_path / "a.nfx").touch()
        (tmp_path / "p").mkdir()
        (tmp_path / "p" / "p.nfx").touch()
        results = {pf.nfx_path.name: pf for pf in plugins.walk_plugins([tmp_path])}
        assert results["a.nfx"].plugin_root is None
        assert results["p.nfx"].plugin_root == (tmp_path / "p").resolve()

    def test_yields_kind_subdir(self, tmp_path):
        (tmp_path / "p" / "ontology").mkdir(parents=True)
        (tmp_path / "p" / "knowledge").mkdir(parents=True)
        (tmp_path / "p" / "ontology" / "p.nfx").touch()
        (tmp_path / "p" / "knowledge" / "p.nfx").touch()
        results = list(plugins.walk_plugins([tmp_path]))
        assert len(results) == 2
        for pf in results:
            assert pf.plugin_root == (tmp_path / "p").resolve()
            assert pf.parent_plugin_root is None

    def test_yields_nested_with_parent(self, tmp_path):
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / "parent.nfx").touch()
        (child / "child.nfx").touch()
        by_name = {pf.nfx_path.name: pf for pf in plugins.walk_plugins([tmp_path])}
        assert by_name["parent.nfx"].parent_plugin_root is None
        assert by_name["child.nfx"].parent_plugin_root == parent.resolve()

    def test_skips_non_nfx_files(self, tmp_path):
        (tmp_path / "p").mkdir()
        (tmp_path / "p" / "p.nfx").touch()
        (tmp_path / "p" / "validators.py").touch()
        (tmp_path / "p" / "README.md").touch()
        names = {pf.nfx_path.name for pf in plugins.walk_plugins([tmp_path])}
        assert names == {"p.nfx"}

    def test_multiple_registry_roots(self, tmp_path):
        r1, r2 = tmp_path / "r1", tmp_path / "r2"
        r1.mkdir()
        r2.mkdir()
        (r1 / "a.nfx").touch()
        (r2 / "b.nfx").touch()
        names = {pf.nfx_path.name for pf in plugins.walk_plugins([r1, r2])}
        assert names == {"a.nfx", "b.nfx"}

    def test_bare_subplugin_in_container_inherits_parent(self, tmp_path):
        parent = tmp_path / "parent"
        container = parent / "plugins"
        container.mkdir(parents=True)
        (parent / "parent.nfx").touch()
        (container / "child.nfx").touch()
        by_name = {pf.nfx_path.name: pf for pf in plugins.walk_plugins([tmp_path])}
        # Bare sub-plugin gets no plugin_root (no validators possible) but
        # still resolves its parent through the `plugins/` container.
        assert by_name["child.nfx"].plugin_root is None
        assert by_name["child.nfx"].parent_plugin_root == parent.resolve()

    def test_dir_form_subplugin_in_container_inherits_parent(self, tmp_path):
        parent = tmp_path / "parent"
        child = parent / "plugins" / "child"
        child.mkdir(parents=True)
        (parent / "parent.nfx").touch()
        (child / "child.nfx").touch()
        by_name = {pf.nfx_path.name: pf for pf in plugins.walk_plugins([tmp_path])}
        assert by_name["child.nfx"].plugin_root == child.resolve()
        assert by_name["child.nfx"].parent_plugin_root == parent.resolve()


def _make_nf_root(tmp_path, name=".nf"):
    root = tmp_path / name
    (root / "ontology").mkdir(parents=True)
    (root / "knowledge").mkdir()
    (root / "validators").mkdir()
    (root / "tests").mkdir()
    return root


class TestConsolidatedRoot:
    def test_is_consolidated(self, tmp_path):
        assert plugins.is_consolidated(tmp_path / ".nf")
        assert not plugins.is_consolidated(tmp_path / "plugins")

    def test_walk_plugins(self, tmp_path):
        root = _make_nf_root(tmp_path)
        (root / "namespace.nfx").touch()
        (root / "ontology" / "Math.nfx").touch()
        (root / "knowledge" / "Antibiotics.nfx").touch()
        (root / "tests" / "stray.nfx").touch()
        (root / "validators" / "Math.py").touch()
        by_name = {pf.nfx_path.name: pf for pf in plugins.walk_plugins([root])}
        assert set(by_name) == {"namespace.nfx", "Math.nfx", "Antibiotics.nfx"}
        math = by_name["Math.nfx"]
        assert math.plugin_root is None and math.parent_plugin_root is None
        assert math.expected_type == "ontology"
        assert math.validators_path == (root / "validators" / "Math.py").resolve()
        assert by_name["Antibiotics.nfx"].expected_type == "knowledge"
        assert by_name["namespace.nfx"].expected_type is None
        assert by_name["namespace.nfx"].validators_path is None

    def test_validators_path_for(self, tmp_path):
        root = _make_nf_root(tmp_path)
        legacy = tmp_path / "plugins"
        (legacy / "p").mkdir(parents=True)
        roots = [root, legacy]
        assert plugins.validators_path_for(root / "ontology" / "Math.nfx", roots) == (
            root / "validators" / "Math.py"
        ).resolve()
        assert plugins.validators_path_for(root / "knowledge" / "K.nfx", roots) == (
            root / "validators" / "K.py"
        ).resolve()
        assert plugins.validators_path_for(root / "namespace.nfx", roots) is None
        assert plugins.validators_path_for(legacy / "p" / "p.nfx", roots) == (
            legacy / "p" / "validators.py"
        ).resolve()
        assert plugins.validators_path_for(legacy / "bare.nfx", roots) is None

    def test_mixed_roots(self, tmp_path):
        root = _make_nf_root(tmp_path)
        legacy = tmp_path / "plugins"
        (legacy / "p").mkdir(parents=True)
        (root / "ontology" / "A.nfx").touch()
        (legacy / "p" / "p.nfx").touch()
        by_root = {}
        for pf in plugins.walk_plugins([legacy, root]):
            by_root.setdefault(pf.registry_root, []).append(pf.nfx_path.name)
        assert by_root == {legacy.resolve(): ["p.nfx"], root.resolve(): ["A.nfx"]}

    def test_load_validators(self, tmp_path):
        root = _make_nf_root(tmp_path)
        nfx_path = root / "ontology" / "Math.nfx"
        nfx_path.touch()
        (root / "validators" / "Math.py").write_text(textwrap.dedent("""
            from neuro.base.plugins import register
            register("Posint", lambda v, _mp: isinstance(v, int) and v > 0)
        """))
        [pf] = plugins.walk_plugins([root])
        assert plugins.load_validators(pf) is True
        assert plugins.lookup("Posint")(3, None) is True


class TestLoadValidatorsAt:
    def test_loads_at_plugin_root(self, tmp_path):
        pkg = tmp_path / "p"
        pkg.mkdir()
        (pkg / "validators.py").write_text(textwrap.dedent("""
            from neuro.base.plugins import register
            register("Posint", lambda v, _mp: isinstance(v, int) and v > 0)
        """))
        assert plugins.load_validators_at(pkg) is True
        assert plugins.lookup("Posint")(7, None) is True

    def test_none_root_returns_false(self):
        assert plugins.load_validators_at(None) is False

    def test_missing_validators_returns_false(self, tmp_path):
        pkg = tmp_path / "p"
        pkg.mkdir()
        assert plugins.load_validators_at(pkg) is False

    def test_idempotent_for_same_root(self, tmp_path):
        pkg = tmp_path / "p"
        pkg.mkdir()
        (pkg / "validators.py").write_text(textwrap.dedent("""
            import itertools
            from neuro.base.plugins import register
            _counter = itertools.count()
            register("Counted", lambda v, _mp: next(_counter) == 0)
        """))
        plugins.load_validators_at(pkg)
        plugins.load_validators_at(pkg)
        assert plugins.lookup("Counted")(None, None) is True


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
