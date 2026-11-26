"""
Unit tests for neuro.base.nfx - Nfx value object + free functions.
"""

import uuid

import pytest

pytestmark = pytest.mark.unit

LOCAL_1 = str(uuid.uuid4())
LOCAL_2 = str(uuid.uuid4())
DEP_1 = str(uuid.uuid4())
DEP_2 = str(uuid.uuid4())
DIRECT_NID = str(uuid.uuid4())
TRANSITIVE_NID = str(uuid.uuid4())
DIRECT_NODE = str(uuid.uuid4())
TRANSITIVE_NODE = str(uuid.uuid4())


# --- Nfx value object ---

def test_nfx_from_dict_parses_dependencies():
    from neuro.base.nfx import Nfx
    doc = Nfx.from_dict({
        "nid": LOCAL_1,
        "name": "X",
        "version": "1.0",
        "dependencies": [f"{DEP_1}@1.2", f"{DEP_2}@3.4"],
        "nodes": [{"nid": LOCAL_2}],
        "relationships": [],
    })
    assert doc.dependencies == ((DEP_1, "1.2"), (DEP_2, "3.4"))
    assert doc.dep_nids == (DEP_1, DEP_2)
    assert doc.node_nids == frozenset({LOCAL_2})


def test_nfx_from_dict_rejects_invalid_nid():
    from neuro.base.nfx import Nfx
    from neuro.utils.exceptions import NfxViolation
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"nid": "not-a-uuid"})


def test_nfx_from_dict_rejects_malformed_dep():
    from neuro.base.nfx import Nfx
    from neuro.utils.exceptions import NfxViolation
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"dependencies": ["no-version-here"]})
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"dependencies": [f"{DEP_1}@"]})
    with pytest.raises(NfxViolation):
        Nfx.from_dict({"dependencies": ["bad-nid@1.0"]})


def test_nfx_from_dict_normalizes_nodes():
    """nid stripped from properties; empty properties dropped; caller's input untouched."""
    from neuro.base.nfx import Nfx
    src_node = {"nid": LOCAL_1, "labels": ["L"], "properties": {"nid": "x", "k": 1}}
    src_empty = {"nid": LOCAL_2, "labels": ["L"], "properties": {"nid": "y"}}
    src_data = {"nodes": [src_node, src_empty], "relationships": []}
    doc = Nfx.from_dict(src_data)
    assert doc.nodes[0]["properties"] == {"k": 1}
    assert "properties" not in doc.nodes[1]
    # caller input untouched
    assert "nid" in src_node["properties"]
    assert "nid" in src_empty["properties"]


def test_nfx_from_dict_normalizes_relationships():
    from neuro.base.nfx import Nfx
    doc = Nfx.from_dict({
        "relationships": [
            {"from": LOCAL_1, "to": LOCAL_2, "type": "USES", "properties": {}},
            {"from": LOCAL_1, "to": LOCAL_2, "type": "OTHER"},
        ],
    })
    assert "properties" not in doc.relationships[0]
    assert "properties" not in doc.relationships[1]


def test_nfx_to_dict_omits_empty_optionals_and_roundtrips():
    from neuro.base.nfx import Nfx
    src = {
        "nid": LOCAL_1,
        "name": "X",
        "version": "1.0",
        "dependencies": [f"{DEP_1}@1.0"],
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"k": 1}}],
        "relationships": [{"from": LOCAL_2, "to": LOCAL_2, "type": "SELF"}],
    }
    out = Nfx.from_dict(src).to_dict()
    assert out["dependencies"] == [f"{DEP_1}@1.0"]
    assert "description" not in out and "hash" not in out
    assert out["nodes"] and out["relationships"]
    # roundtrip stability
    assert Nfx.from_dict(out).to_dict() == out


def test_nfx_to_dict_omits_empty_nodes_and_relationships():
    from neuro.base.nfx import Nfx
    out = Nfx(nid=LOCAL_1).to_dict()
    assert out == {"nid": LOCAL_1}


def test_nfx_to_dict_canonicalizes_node_key_order():
    from neuro.base.nfx import Nfx, lint_format
    out = Nfx.from_dict({
        "type": "ontology", "nid": LOCAL_1, "version": "1.0", "name": "X",
        "nodes": [{"properties": {"k": 1}, "labels": ["L"], "nid": LOCAL_2}],
    }).to_dict()
    assert list(out["nodes"][0]) == ["nid", "labels", "properties"]
    assert lint_format(out)["key_order"] == []


def test_nfx_to_dict_canonicalizes_relationship_key_order():
    from neuro.base.nfx import Nfx, lint_format
    out = Nfx.from_dict({
        "type": "ontology", "nid": LOCAL_1, "version": "1.0", "name": "X",
        "nodes": [{"nid": LOCAL_2, "labels": ["L"]}],
        "relationships": [{"to": LOCAL_2, "from": LOCAL_2, "type": "SELF"}],
    }).to_dict()
    assert list(out["relationships"][0]) == ["from", "to", "type"]
    assert lint_format(out)["key_order"] == []


def test_nfx_to_dict_keeps_unknown_node_key():
    """An unknown key is a lint violation, so the writer must not hide it."""
    from neuro.base.nfx import Nfx, lint_format
    out = Nfx.from_dict({
        "type": "ontology", "nid": LOCAL_1, "version": "1.0", "name": "X",
        "nodes": [{"bogus": 1, "nid": LOCAL_2, "labels": ["L"]}],
    }).to_dict()
    assert list(out["nodes"][0]) == ["nid", "labels", "bogus"]
    assert lint_format(out)["unknown_keys"] == [{"where": "nodes[0]", "keys": ["bogus"]}]


def test_dumps_keeps_non_ascii_literal():
    from neuro.base.nfx import Nfx, dumps
    text = dumps(Nfx.from_dict({
        "type": "knowledge", "nid": LOCAL_1, "version": "1.0", "name": "X",
        "description": "an em-dash — and a š",
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"name_sl": "Tuš"}}],
    }))
    assert "—" in text and "Tuš" in text
    assert "\\u" not in text


def test_order_labels_demotes_module_marker():
    from neuro.base.nfx import order_labels
    out = order_labels([
        {"nid": LOCAL_1, "labels": ["Metaontology", "OntologyRelationship"]},
        {"nid": LOCAL_2, "labels": ["Metaontology", "OntologyNode"]},
    ])
    assert [n["labels"] for n in out] == [
        ["OntologyRelationship", "Metaontology"], ["OntologyNode", "Metaontology"]]


def test_order_labels_keeps_a_universal_only_node():
    """Demoting every label would leave no class to anchor the import MERGE."""
    from neuro.base.nfx import order_labels
    out = order_labels([{"nid": LOCAL_1, "labels": ["OntologyNode"]},
                        {"nid": LOCAL_2, "labels": ["OntologyNode"]}])
    assert [n["labels"] for n in out] == [["OntologyNode"], ["OntologyNode"]]


def test_nfx_is_frozen():
    from neuro.base.nfx import Nfx
    doc = Nfx(nid=LOCAL_1)
    with pytest.raises(Exception):
        doc.nid = LOCAL_2  # frozen dataclass


def test_nfx_hash_field_roundtrip():
    from neuro.base.nfx import Nfx
    doc = Nfx.from_dict({"nid": LOCAL_1, "hash": "abc123", "nodes": [], "relationships": []})
    assert doc.hash == "abc123"
    assert doc.to_dict()["hash"] == "abc123"


# --- validate (referential integrity) ---

def test_validate_foreign_relationship():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}],
        "relationships": [
            {"from": LOCAL_1, "to": DEP_1, "type": "USES"},
            {"from": DEP_1, "to": DEP_2, "type": "RELATES"},
        ],
    })
    result = validate(doc, dependency_nids={DEP_1, DEP_2})
    assert len(result["foreign"]) == 1
    assert result["foreign"][0]["type"] == "RELATES"
    assert result["unresolved"] == []
    assert result["invalid_nids"] == []


def test_validate_unresolved_relationship():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": "unknown", "type": "RELATES"}],
    })
    result = validate(doc)
    assert len(result["unresolved"]) == 1
    assert result["foreign"] == []
    assert result["invalid_nids"] == ["unknown"]


def test_validate_invalid_nid():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [
            {"nid": "not-a-uuid"},
            {"nid": "550e8400-e29b-41d4-a716-446655440000"},
        ],
        "relationships": [],
    })
    result = validate(doc)
    assert result["invalid_nids"] == ["not-a-uuid"]


def test_validate_duplicate_nid():
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}, {"nid": LOCAL_1}, {"nid": LOCAL_1}],
    })
    assert validate(doc)["duplicate_nids"] == [LOCAL_1, LOCAL_1]


def test_validate_duplicate_relationship():
    """Same (from, to, type) twice is a duplicate; a different type is not."""
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}],
        "relationships": [
            {"from": LOCAL_1, "to": LOCAL_2, "type": "USES"},
            {"from": LOCAL_1, "to": LOCAL_2, "type": "OTHER"},
            {"from": LOCAL_1, "to": LOCAL_2, "type": "USES", "properties": {"k": 1}},
        ],
    })
    result = validate(doc)
    assert result["duplicate_relationships"] == [doc.relationships[2]]
    assert result["duplicate_nids"] == []


def test_validate_missing_required():
    """A nameless document reports `name` - the field's own regression guard.

    Every other assertion on this list checks that it is *empty*, so dropping
    `name` from `_REQUIRED_FIELDS` would leave the suite green while restoring
    the orphaning import.
    """
    from neuro.base.nfx import Nfx, validate
    doc = Nfx.from_dict({"type": "ontology", "nid": LOCAL_1, "version": "1.0"})
    assert validate(doc)["missing_required"] == ["name"]
    assert validate(Nfx.from_dict({}))["missing_required"] == [
        "type", "nid", "version", "name"]


def test_validate_untaggable_name():
    """An ontology's name has to survive `git tag <name>/<version>`."""
    from neuro.base.nfx import Nfx, validate
    base = {"type": "ontology", "nid": LOCAL_1, "version": "1.0"}
    assert validate(Nfx.from_dict({**base, "name": "NLZOH branches"}))[
        "untaggable_name"] == "NLZOH branches"
    assert validate(Nfx.from_dict({**base, "name": "some-system"}))["untaggable_name"] is None
    assert validate(Nfx.from_dict({**base, "name": "ISO-639"}))["untaggable_name"] is None
    # knowledge is never tagged, so the same name is fine there
    assert validate(Nfx.from_dict({
        **base, "type": "knowledge", "name": "NLZOH branches"}))["untaggable_name"] is None


def test_extensions():
    """A re-declared node of a dependency: restating it adds nothing, a label
    or key beyond it is a contribution, and a clash or a schema node refuses."""
    from neuro.base.nfx import Nfx, extensions

    def module(kind, name, node):
        return Nfx.from_dict({"type": kind, "nid": str(uuid.uuid4()), "version": "1.0",
                              "name": name, "nodes": [node]})

    owned = {"nid": LOCAL_2, "labels": ["Thing"], "properties": {"title": "t", "rank": 1}}
    owner = module("knowledge", "owner", owned)
    deps = {LOCAL_2: [(owner, owner.nodes[0])]}

    assert extensions(module("knowledge", "k", {**owned, "properties": {"title": "t"}}), deps) == ({}, [])
    added, issues = extensions(module("knowledge", "k", {
        "nid": LOCAL_2, "labels": ["Thing", "Tiddler"], "properties": {"title": "t", "text": "x"}}), deps)
    assert issues == []
    assert added[LOCAL_2]["labels"] == ["Tiddler"] and added[LOCAL_2]["properties"] == {"text": "x"}
    assert added[LOCAL_2]["declared"] == {"labels": ["Thing"], "properties": {"title": "t", "rank": 1}}

    added, issues = extensions(module("knowledge", "k", {**owned, "properties": {"rank": 2}}), deps)
    assert added == {} and "'rank' is declared by owner" in issues[0]

    schema = module("ontology", "onto", owned)
    added, issues = extensions(module("knowledge", "k", {**owned, "labels": ["Thing", "Tiddler"]}),
                               {LOCAL_2: [(schema, schema.nodes[0])]})
    assert added == {} and "ontology onto cannot be extended" in issues[0]


def test_is_taggable():
    from neuro.base.nfx import is_taggable
    assert all(is_taggable(n) for n in ("Metaontology", "some-system", "ISO-639", "a.b"))
    assert not any(is_taggable(n) for n in (
        "has space", "a/b", "-lead", "trail-", "dot.", "a..b", "x.lock", "~tilde", "q?", ""))


# --- namespace declaration (type: "namespace") ---

NS_BASE = {"type": "namespace", "nid": LOCAL_1, "version": "1.0", "name": "Root"}


def test_nfx_namespace_roundtrip():
    """The silent-drop trap: an empty token must survive write → read as
    `""`, never as an absent key, and `was` must come back intact."""
    from neuro.base.nfx import Nfx, dumps
    doc = Nfx.from_dict({**NS_BASE, "namespace": ""})
    assert doc.namespace == ""
    out = doc.to_dict()
    assert out["namespace"] == ""
    assert "was" not in out
    assert Nfx.from_dict(out).namespace == ""
    import json
    again = Nfx.from_dict(json.loads(dumps(Nfx.from_dict(
        {**NS_BASE, "namespace": "new", "was": ["old"], "dependencies": [f"{DEP_1}@1.0"]}))))
    assert again.namespace == "new"
    assert again.was == ("old",)
    assert again.dependencies == ((DEP_1, "1.0"),)


def test_nfx_namespace_absent_is_none():
    from neuro.base.nfx import Nfx
    assert Nfx.from_dict({"type": "ontology", "nid": LOCAL_1}).namespace is None
    assert "namespace" not in Nfx.from_dict({"type": "ontology", "nid": LOCAL_1}).to_dict()


def test_nfx_from_dict_rejects_malformed_namespace():
    from neuro.base.nfx import Nfx
    from neuro.utils.exceptions import NfxViolation
    with pytest.raises(NfxViolation):
        Nfx.from_dict({**NS_BASE, "namespace": 3})
    with pytest.raises(NfxViolation):
        Nfx.from_dict({**NS_BASE, "namespace": "x", "was": "old"})


def test_is_namespace_token():
    from neuro.base.nfx import is_namespace_token
    assert all(is_namespace_token(t) for t in ("", "lab", "lab-ds", "x-y", "a1"))
    assert not any(is_namespace_token(t) for t in (
        "Lab", "lab_", "-x", "x-", "a--b", "a b", "a.b", "a/b"))


def test_validate_namespace_clean():
    from neuro.base.nfx import Nfx, validate
    assert validate(Nfx.from_dict({**NS_BASE, "namespace": ""}))["namespace"] == []
    assert validate(Nfx.from_dict(
        {**NS_BASE, "namespace": "abc", "was": ["xyz"]}))["namespace"] == []


def test_validate_namespace_issues():
    from neuro.base.nfx import Nfx, validate
    def issues(d):
        return validate(Nfx.from_dict(d))["namespace"]
    assert any("no 'namespace' key" in m for m in issues(NS_BASE))
    assert any("invalid namespace token" in m for m in issues({**NS_BASE, "namespace": "Abc"}))
    assert any("repeats the current" in m for m in issues(
        {**NS_BASE, "namespace": "abc", "was": ["abc"]}))
    assert any("twice" in m for m in issues(
        {**NS_BASE, "namespace": "abc", "was": ["old", "old"]}))
    assert any("invalid retired token" in m for m in issues(
        {**NS_BASE, "namespace": "abc", "was": [""]}))
    assert any("carries 'nodes'" in m for m in issues(
        {**NS_BASE, "namespace": "abc", "nodes": [{"nid": LOCAL_2}]}))
    assert any("carries 'hash'" in m for m in issues(
        {**NS_BASE, "namespace": "abc", "hash": "abc"}))


def test_validate_namespace_keys_misplaced():
    from neuro.base.nfx import Nfx, validate
    base = {"type": "ontology", "nid": LOCAL_1, "version": "1.0", "name": "X"}
    assert validate(Nfx.from_dict(base))["namespace"] == []
    msgs = validate(Nfx.from_dict({**base, "namespace": "x", "was": ["y"]}))["namespace"]
    assert len(msgs) == 2 and all("only a namespace file" in m for m in msgs)


def test_validate_namespace_type_allowed():
    from neuro.base.nfx import Nfx, validate
    assert validate(Nfx.from_dict({**NS_BASE, "namespace": ""}))["invalid_type"] is None


def test_lint_format_namespace_key_order():
    from neuro.base.nfx import lint_format
    ok = {"type": "namespace", "nid": LOCAL_1, "version": "1.0", "name": "R",
          "namespace": "", "dependencies": []}
    assert lint_format(ok)["key_order"] == [] and lint_format(ok)["unknown_keys"] == []
    bad = {"type": "namespace", "nid": LOCAL_1, "dependencies": [], "namespace": ""}
    assert lint_format(bad)["key_order"]


def test_nfx_released_roundtrip():
    """Absent stays absent, `false` survives write → read, and sits after `was`."""
    import json
    from neuro.base.nfx import Nfx, dumps, lint_format
    plain = Nfx.from_dict({**NS_BASE, "namespace": "t"})
    assert plain.released is None and "released" not in plain.to_dict()
    doc = Nfx.from_dict({**NS_BASE, "namespace": "t", "was": ["old"], "released": False,
                         "dependencies": [f"{DEP_1}@1.0"]})
    assert doc.released is False
    raw = json.loads(dumps(doc))
    assert raw["released"] is False
    assert list(raw).index("was") < list(raw).index("released") < list(raw).index("dependencies")
    assert lint_format(raw)["key_order"] == [] and lint_format(raw)["unknown_keys"] == []
    assert Nfx.from_dict(raw).released is False


def test_nfx_released_issues():
    from neuro.base.nfx import Nfx, validate
    from neuro.utils.exceptions import NfxViolation
    assert validate(Nfx.from_dict({**NS_BASE, "namespace": "t", "released": False}))["namespace"] == []
    # one spelling: a released root omits the key
    assert any("only as false" in m for m in validate(
        Nfx.from_dict({**NS_BASE, "namespace": "t", "released": True}))["namespace"])
    # only a namespace file says it
    module = {"type": "ontology", "nid": LOCAL_1, "version": "1.0", "name": "X", "released": False}
    assert any("'released' key on a ontology document" in m for m in validate(Nfx.from_dict(module))["namespace"])
    with pytest.raises(NfxViolation):
        Nfx.from_dict({**NS_BASE, "namespace": "t", "released": "no"})


def test_lint_format_flags_empty_arrays():
    from neuro.base.nfx import lint_format
    assert lint_format({"nodes": [], "relationships": []})["empty"] == ["nodes", "relationships"]
    assert lint_format({"nodes": [{"nid": LOCAL_1}], "relationships": []})["empty"] == ["relationships"]
    assert lint_format({})["empty"] == []
    assert lint_format({
        "nodes": [{"nid": LOCAL_1}],
        "relationships": [{"from": LOCAL_1, "to": LOCAL_1, "type": "SELF"}],
    })["empty"] == []


def test_validate_accepts_transitive_endpoint():
    """A relationship from a local node to a transitive-dep node validates."""
    from neuro.base.nfx import Nfx, NfxTree, validate
    registry = {
        DIRECT_NID: Nfx.from_dict({
            "nid": DIRECT_NID,
            "nodes": [{"nid": DIRECT_NODE}],
            "dependencies": [f"{TRANSITIVE_NID}@1.0"],
        }),
        TRANSITIVE_NID: Nfx.from_dict({
            "nid": TRANSITIVE_NID,
            "nodes": [{"nid": TRANSITIVE_NODE}],
            "dependencies": [],
        }),
    }
    doc = Nfx.from_dict({
        "nid": LOCAL_1,
        "dependencies": [f"{DIRECT_NID}@1.0"],
        "nodes": [{"nid": LOCAL_2}],
        "relationships": [{"from": LOCAL_2, "to": TRANSITIVE_NODE, "type": "USES"}],
    })
    tree = NfxTree(doc, registry.get)
    result = validate(doc, dependency_nids=tree.all_node_nids(scope="dependencies"))
    assert result["unresolved"] == []
    assert result["foreign"] == []


# --- NfxTree (eager DAG) ---

def test_nfx_tree_collects_transitive_node_nids():
    from neuro.base.nfx import Nfx, NfxTree
    registry = {
        DIRECT_NID: Nfx.from_dict({
            "nid": DIRECT_NID,
            "nodes": [{"nid": DIRECT_NODE}],
            "dependencies": [f"{TRANSITIVE_NID}@1.0"],
        }),
        TRANSITIVE_NID: Nfx.from_dict({
            "nid": TRANSITIVE_NID,
            "nodes": [{"nid": TRANSITIVE_NODE}],
            "dependencies": [],
        }),
    }
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{DIRECT_NID}@1.0"]})
    tree = NfxTree(root, registry.get)
    assert tree.all_node_nids(scope="dependencies") == {DIRECT_NODE, TRANSITIVE_NODE}
    assert tree.all_node_nids(scope="root") == set()
    assert tree.all_node_nids(scope="all") == {DIRECT_NODE, TRANSITIVE_NODE}


def test_nfx_tree_rejects_cycle():
    from neuro.base.nfx import Nfx, NfxTree
    from neuro.utils.exceptions import NfxCycle
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    registry = {
        a: Nfx.from_dict({"nid": a, "dependencies": [f"{b}@1.0"]}),
        b: Nfx.from_dict({"nid": b, "dependencies": [f"{a}@1.0"]}),
    }
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{a}@1.0"]})
    with pytest.raises(NfxCycle) as exc:
        NfxTree(root, registry.get)
    assert exc.value.args[0][0] == exc.value.args[0][-1]


def test_nfx_tree_records_missing():
    from neuro.base.nfx import Nfx, NfxTree
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{DEP_1}@1.0"]})
    tree = NfxTree(root, lambda _nid: None)
    assert tree.missing == {DEP_1}
    assert set(tree.modules) == {LOCAL_1}
    assert tree.all_node_nids() == set()


def test_nfx_tree_redundant_directs_flags_indirect_overlap():
    """A direct dep that's also reachable via another direct is redundant.

    Mirrors a real tree, which declares Biology, Time, metaontology directly,
    but Biology→Time→metaontology already covers the latter two."""
    from neuro.base.nfx import Nfx, NfxTree
    META = str(uuid.uuid4())
    TIME = str(uuid.uuid4())
    BIO = str(uuid.uuid4())
    registry = {
        META: Nfx.from_dict({"nid": META, "dependencies": []}),
        TIME: Nfx.from_dict({"nid": TIME, "dependencies": [f"{META}@1.0"]}),
        BIO: Nfx.from_dict({"nid": BIO, "dependencies": [f"{TIME}@1.0", f"{META}@1.0"]}),
    }
    root = Nfx.from_dict({
        "nid": LOCAL_1,
        "dependencies": [f"{BIO}@1.0", f"{TIME}@1.0", f"{META}@1.0"],
    })
    tree = NfxTree(root, registry.get)
    assert tree.redundant_directs() == {TIME, META}


def test_nfx_tree_no_redundancy_for_independent_directs():
    from neuro.base.nfx import Nfx, NfxTree
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    registry = {
        a: Nfx.from_dict({"nid": a, "dependencies": []}),
        b: Nfx.from_dict({"nid": b, "dependencies": []}),
    }
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{a}@1.0", f"{b}@1.0"]})
    tree = NfxTree(root, registry.get)
    assert tree.redundant_directs() == set()


def test_nfx_tree_topo_order():
    from neuro.base.nfx import Nfx, NfxTree
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    registry = {
        a: Nfx.from_dict({"nid": a, "dependencies": []}),
        b: Nfx.from_dict({"nid": b, "dependencies": [f"{a}@1.0"]}),
    }
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{b}@1.0"]})
    order = NfxTree(root, registry.get).topo_order()
    assert order.index(a) < order.index(b) < order.index(LOCAL_1)


def test_nfx_tree_contains_and_iter():
    from neuro.base.nfx import Nfx, NfxTree
    a = str(uuid.uuid4())
    registry = {a: Nfx.from_dict({"nid": a, "dependencies": []})}
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{a}@1.0"]})
    tree = NfxTree(root, registry.get)
    assert a in tree
    assert LOCAL_1 in tree
    assert set(tree) == {a, LOCAL_1}


def test_nfx_tree_extra_deps_inject_implicit_edge():
    from neuro.base.nfx import Nfx, NfxTree
    parent = str(uuid.uuid4())
    registry = {parent: Nfx.from_dict({"nid": parent, "dependencies": []})}
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": []})
    extra = {LOCAL_1: [parent]}
    tree = NfxTree(root, registry.get, extra_deps=lambda nid: extra.get(nid, []))
    # Parent appears in modules and in root's edges, even though dep_nids is empty.
    assert parent in tree
    assert parent in tree.edges[LOCAL_1]
    assert tree.topo_order().index(parent) < tree.topo_order().index(LOCAL_1)


def test_nfx_tree_extra_deps_dedupes_with_explicit():
    from neuro.base.nfx import Nfx, NfxTree
    parent = str(uuid.uuid4())
    registry = {parent: Nfx.from_dict({"nid": parent, "dependencies": []})}
    root = Nfx.from_dict({"nid": LOCAL_1, "dependencies": [f"{parent}@1.0"]})
    extra = {LOCAL_1: [parent]}
    tree = NfxTree(root, registry.get, extra_deps=lambda nid: extra.get(nid, []))
    assert tree.edges[LOCAL_1].count(parent) == 1


# --- lint_format (raw-dict format checks) ---

def test_lint_format_key_order_top_level():
    from neuro.base.nfx import lint_format
    data = {"nid": LOCAL_1, "nodes": [], "version": "1.0", "relationships": []}
    result = lint_format(data)
    assert len(result["key_order"]) == 1
    assert result["key_order"][0]["where"] == "top-level"
    assert result["unknown_keys"] == []


def test_lint_format_key_order_node():
    from neuro.base.nfx import lint_format
    data = {
        "nodes": [{"labels": ["X"], "nid": LOCAL_1}],
        "relationships": [],
    }
    result = lint_format(data)
    assert len(result["key_order"]) == 1
    assert result["key_order"][0]["where"] == "nodes[0]"


def test_lint_format_key_order_relationship():
    from neuro.base.nfx import lint_format
    data = {
        "nodes": [{"nid": LOCAL_1}, {"nid": LOCAL_2}],
        "relationships": [{"to": LOCAL_2, "from": LOCAL_1, "type": "USES"}],
    }
    result = lint_format(data)
    assert len(result["key_order"]) == 1
    assert result["key_order"][0]["where"] == "relationships[0]"


def test_lint_format_unknown_key_top_level():
    from neuro.base.nfx import lint_format
    data = {"nid": LOCAL_1, "bogus": 1, "nodes": [], "relationships": []}
    result = lint_format(data)
    assert result["unknown_keys"] == [{"where": "top-level", "keys": ["bogus"]}]


def test_lint_format_unknown_key_node():
    from neuro.base.nfx import lint_format
    data = {
        "nodes": [{"nid": LOCAL_1, "labels": ["X"], "extra": 1}],
        "relationships": [],
    }
    result = lint_format(data)
    assert result["unknown_keys"] == [{"where": "nodes[0]", "keys": ["extra"]}]


def test_lint_format_accepts_canonical_key_order():
    from neuro.base.nfx import lint_format
    data = {
        "type": "ontology",
        "nid": LOCAL_1,
        "version": "1.0",
        "name": "X",
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"a": 1}}],
        "relationships": [{"from": LOCAL_2, "to": LOCAL_2, "type": "SELF"}],
    }
    result = lint_format(data)
    assert result["key_order"] == []
    assert result["unknown_keys"] == []


# --- read / write roundtrip ---

def test_read_write_roundtrip(tmp_path):
    from neuro.base.nfx import Nfx, read, write
    src = Nfx.from_dict({
        "nid": LOCAL_1,
        "name": "Test",
        "version": "1.0",
        "dependencies": [f"{DEP_1}@1.0"],
        "nodes": [{"nid": LOCAL_2, "labels": ["L"], "properties": {"k": 1}}],
        "relationships": [{"from": LOCAL_2, "to": LOCAL_2, "type": "SELF"}],
    })
    p = tmp_path / "x.nfx"
    write(p, src)
    assert read(p) == src
