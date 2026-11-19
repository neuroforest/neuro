"""
Unit tests for neuro.base.nf_import - legacy plugins root → `.nf` root.
"""

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from neuro.base import nf_import, nfx

pytestmark = pytest.mark.unit

PARENT_NID = str(uuid.uuid4())

_TEST_TEXT = '''from pathlib import Path

from neuro.base import plugins

_ALPHA_NFX = Path(__file__).with_name("alpha.nfx")


def _load():
    plugins.load_plugin_at(_ALPHA_NFX)
'''


def _write_nfx(path, *, kind, name, hash="", dependencies=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"type": kind, "nid": str(uuid.uuid4()), "version": "1.0", "name": name}
    if dependencies:
        doc["dependencies"] = list(dependencies)
    if hash:
        doc["hash"] = hash
    path.write_text(json.dumps(doc))
    return doc["nid"]


def _legacy(tmp_path):
    """A legacy root in every layout: bare, flat-dir with validators + test
    and a knowledge sibling, kind-subdir, and a nested sub-plugin."""
    root = tmp_path / "plugins"
    validators = b"VALIDATORS = 1\n"
    _write_nfx(root / "bare.nfx", kind="ontology", name="Bare")
    _write_nfx(root / "alpha" / "alpha.nfx", kind="ontology", name="Alpha",
               hash=hashlib.sha256(validators).hexdigest())
    _write_nfx(root / "alpha" / "facts.nfx", kind="knowledge", name="Facts")
    (root / "alpha" / "validators.py").write_bytes(validators)
    (root / "alpha" / "test_validators.py").write_text(_TEST_TEXT)
    _write_nfx(root / "std" / "std.nfx", kind="ontology", name="Std")
    _write_nfx(root / "std" / "knowledge" / "codes.nfx", kind="knowledge", name="Codes")
    parent_nid = _write_nfx(root / "outer" / "outer.nfx", kind="ontology", name="Outer")
    _write_nfx(root / "outer" / "inner" / "inner.nfx", kind="ontology", name="Inner")
    (root / "ruff.toml").write_text("[lint]\n")
    (root / ".scripts").mkdir()
    (root / ".scripts" / "validate.py").write_text("")
    (root / "alpha" / "__pycache__").mkdir()
    (root / "alpha" / "__pycache__" / "validators.cpython-314.pyc").write_bytes(b"")
    return root, parent_nid


def _namespace():
    return nf_import.namespace_doc(str(uuid.uuid4()), PARENT_NID, "1.0")


def test_plan_import(tmp_path):
    root, parent_nid = _legacy(tmp_path)
    mapping = nf_import.plan_import(root, _namespace())

    assert mapping.issues == []
    rels = {str(m.rel) for m in mapping.moves}
    assert rels == {
        "namespace.nfx", "ruff.toml",
        "ontology/bare.nfx", "ontology/alpha.nfx", "ontology/std.nfx",
        "ontology/outer.nfx", "ontology/inner.nfx",
        "knowledge/facts.nfx", "knowledge/codes.nfx",
        "validators/alpha.py", "tests/test_alpha.py",
    }
    assert [p.name for p in mapping.skipped] == ["validate.py"]
    tags = {m.tag for m in mapping.modules}
    assert "ontology/alpha/1.0" in tags and "knowledge/codes/1.0" in tags

    inner = next(m for m in mapping.modules if m.rel.name == "inner.nfx")
    assert (parent_nid, "1.0") in nfx.Nfx.from_dict(json.loads(inner.content)).dependencies
    assert inner.note == "pins parent outer@1.0"

    ns = nfx.Nfx.from_dict(json.loads(mapping.moves[0].content))
    assert ns.is_namespace and ns.namespace == "" and ns.name == "Root"
    assert ns.dependencies == ((PARENT_NID, "1.0"),)


def test_plan_import_unmapped(tmp_path):
    root, _ = _legacy(tmp_path)
    (root / "alpha" / "notes.md").write_text("")
    mapping = nf_import.plan_import(root, _namespace())
    assert mapping.issues == ["alpha/notes.md: unmapped"]


def test_plan_import_hash_mismatch(tmp_path):
    root, _ = _legacy(tmp_path)
    (root / "alpha" / "validators.py").write_bytes(b"CHANGED = 1\n")
    mapping = nf_import.plan_import(root, _namespace())
    assert len(mapping.issues) == 1
    assert "sha256 differs from alpha.nfx's hash" in mapping.issues[0]


def test_plan_import_validators_without_ontology(tmp_path):
    root = tmp_path / "plugins"
    _write_nfx(root / "kb" / "kb.nfx", kind="knowledge", name="Kb")
    (root / "kb" / "validators.py").write_text("")
    mapping = nf_import.plan_import(root, _namespace())
    assert mapping.issues == ["kb/validators.py: needs exactly one ontology in its plugin to own it, found 0"]


def test_rewrite_test():
    out = nf_import.rewrite_test(_TEST_TEXT, "alpha")
    assert '_ALPHA_VALIDATORS = Path(__file__).parents[1] / "validators" / "alpha.py"' in out
    assert "plugins.load_validators_file(_ALPHA_VALIDATORS)" in out
    assert "_NFX" not in out

    with pytest.raises(ValueError, match="not beta.nfx"):
        nf_import.rewrite_test(_TEST_TEXT, "beta")
    with pytest.raises(ValueError, match="beyond locating"):
        nf_import.rewrite_test(_TEST_TEXT + "\nprint(_ALPHA_NFX)\n", "alpha")


def test_sync(tmp_path):
    root, _ = _legacy(tmp_path)
    dst = tmp_path / "home" / ".nf"
    mapping = nf_import.plan_import(root, _namespace())

    assert len(nf_import.diff(mapping, dst)["new"]) == len(mapping.moves)
    nf_import.sync(mapping, dst)
    (dst / "ontology" / "gone.nfx").write_text("{}")
    (dst / ".git").mkdir()
    (dst / ".git" / "HEAD").write_text("")

    delta = nf_import.sync(mapping, dst)
    assert delta["stale"] == [Path("ontology/gone.nfx")]
    assert delta["new"] == delta["changed"] == []
    assert not (dst / "ontology" / "gone.nfx").exists()
    assert (dst / ".git" / "HEAD").exists()
    assert len(nf_import.diff(mapping, dst)["same"]) == len(mapping.moves)


def test_verify(tmp_path):
    root, _ = _legacy(tmp_path)
    staged = tmp_path / "stage" / ".nf"
    mapping = nf_import.plan_import(root, _namespace())
    nf_import.stage(mapping, staged)
    assert nf_import.verify(staged, root) == []

    (staged / "ontology" / "bare.nfx").unlink()
    (staged / "validators" / "alpha.py").write_text("X = 2\n")
    issues = nf_import.verify(staged, root)
    assert "bare.nfx: missing from the copy" in issues
    assert "alpha.nfx: hash does not match alpha.py" in issues
