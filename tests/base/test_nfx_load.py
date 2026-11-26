"""
Tests for neuro.base.nfx_load - what an import retracts, read from the release
tags of a git-tracked `.nf` root.
"""

import os
import subprocess
import uuid

import pytest

from neuro.base import nfx, nfx_load
from neuro.utils import exceptions

_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.org"}


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], env={**os.environ, **_ENV},
                          capture_output=True, text=True, check=True).stdout


class _Tree:
    """A `.nf` root that is its own repository, holding one ontology `p`."""

    def __init__(self, path):
        self.path = path
        path.mkdir()
        _git(path, "init", "-q", "-b", "master")
        _git(path, "config", "core.hooksPath", "/dev/null")  # no global hooks in tests
        self.nid = str(uuid.uuid4())
        self.file = path / "ontology" / "p.nfx"

    def release(self, version, nodes, relationships=(), tag=True):
        self.file.parent.mkdir(exist_ok=True)
        nfx.write(self.file, nfx.Nfx(
            nid=self.nid, type="ontology", name="p", version=version,
            nodes=tuple(nodes), relationships=tuple(relationships),
        ))
        _git(self.path, "add", "ontology/p.nfx")
        _git(self.path, "commit", "-q", "-m", f"RELEASE: ontology p {version}")
        if tag:
            _git(self.path, "tag", "-a", f"ontology/p/{version}", "-m", version)
        return self.file


@pytest.fixture
def tree(tmp_path):
    return _Tree(tmp_path / ".nf")


def _node(nid, label, labels=("OntologyNode",), **properties):
    return {"nid": nid, "labels": list(labels), "properties": {"label": label, **properties}}


def _state(nb, nid):
    rows = nb.get_data("MATCH (n {nid: $nid}) RETURN labels(n) AS labels, properties(n) AS props", {"nid": nid})
    return (set(rows[0]["labels"]), rows[0]["props"]) if rows else None


def _edges(nb, from_nid):
    return {(r["type"], r["to"]) for r in nb.get_data(
        "MATCH ({nid: $nid})-[r]->(b) RETURN type(r) AS type, b.nid AS to", {"nid": from_nid})}


def test_write_document(nb_meta, tree):
    """An import takes back what the previous release declared and this one
    does not - and nothing else."""
    a, b, c, d = (str(uuid.uuid4()) for _ in range(4))
    nb_meta.metaontology.import_nfx(tree.release("1.0", [
        _node(a, "A", ["OntologyNode", "Extra"], color="red", shape="round"),
        _node(b, "B"), _node(c, "C"), _node(d, "D"),
    ], [
        {"from": a, "to": b, "type": "SUBCLASS_OF", "properties": {"weight": 1, "note": "x"}},
        {"from": a, "to": c, "type": "SUBCLASS_OF"},
        {"from": d, "to": a, "type": "SUBCLASS_OF"},
    ]))
    # What nobody declared: a label, a property and two edges put there by hand.
    nb_meta.run_query(
        """
        MATCH (a {nid: $a}), (b {nid: $b}), (c {nid: $c})
        SET a:Curated, a.owner = 'hand'
        CREATE (a)-[:RELATED_TO]->(c)
        CREATE (:MetricDefinition {nid: 'metric', label: 'M'})-[:APPLIES_TO]->(b)
        """,
        {"a": a, "b": b, "c": c},
    )

    # 1.1 drops A's `Extra` label and `shape`, the edge A → C, a property of
    # the edge A → B, and the nodes B and D with the edges that touched them.
    report = nb_meta.metaontology.import_nfx(tree.release("1.1", [
        _node(a, "A", color="red"), _node(c, "C"),
    ]))

    labels, props = _state(nb_meta, a)
    assert labels == {"OntologyNode", "Curated"}
    assert props == {"nid": a, "label": "A", "color": "red", "owner": "hand"}
    assert _edges(nb_meta, a) == {("RELATED_TO", c)}
    assert _state(nb_meta, b) is not None, "an edge from outside holds B"
    assert _state(nb_meta, d) is None, "nothing is left on D"
    assert report["orphaned"] == [("B", 1)] and report["removed"] == ["D"]
    assert report["edges_pruned"] == 3

    # 1.2 keeps the edge and drops one of its properties.
    nb_meta.metaontology.import_nfx(tree.release("1.2", [_node(a, "A", color="red"), _node(c, "C")], [
        {"from": a, "to": c, "type": "SUBCLASS_OF", "properties": {"weight": 1, "note": "x"}},
    ]))
    nb_meta.run_query("MATCH ({nid: $a})-[r:SUBCLASS_OF]->() SET r.seen = true", {"a": a})
    nb_meta.metaontology.import_nfx(tree.release("1.3", [_node(a, "A", color="red"), _node(c, "C")], [
        {"from": a, "to": c, "type": "SUBCLASS_OF", "properties": {"weight": 2}},
    ]))
    edge = nb_meta.get_data("MATCH ({nid: $a})-[r:SUBCLASS_OF]->() RETURN properties(r) AS p", {"a": a})
    assert edge[0]["p"] == {"weight": 2, "seen": True}


def test_previous_document(nb_meta, tree):
    """The previous version is the release the base holds; one that cannot be
    read refuses the import, unless no release lies between."""
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    policy = nfx_load.POLICIES["ontology"]

    path = tree.release("1.0", [_node(a, "A"), _node(b, "B")], tag=False)
    doc = nfx.read(path)
    assert nfx_load.previous_document(nb_meta, path, policy, doc) == nfx_load.Previous()

    nb_meta.metaontology.import_nfx(path)
    # Loaded and imported version agree and no tag exists: nothing to retract.
    assert nfx_load.previous_document(nb_meta, path, policy, doc) == nfx_load.Previous()

    path = tree.release("1.1", [_node(a, "A")], tag=False)
    with pytest.raises(exceptions.NfxViolation, match="cannot be read"):
        nb_meta.metaontology.import_nfx(path)
    assert _state(nb_meta, b) is not None, "a refused import writes nothing"

    _git(tree.path, "tag", "-a", "ontology/p/1.0", "-m", "1.0", "HEAD~1")
    previous = nfx_load.previous_document(nb_meta, path, policy, nfx.read(path))
    assert previous.doc.version == "1.0" and previous.doc.node_nids == {a, b}

    # A document in no repository takes the base as its previous version, and
    # so does the metaontology wherever it lives.
    loose = tree.path.parent / "p.nfx"
    loose.write_text(path.read_text())
    assert nfx_load.previous_document(nb_meta, loose, policy, nfx.read(loose)).graph
    assert nfx_load.previous_document(
        nb_meta, path, nfx_load.POLICIES["metaontology"], nfx.read(path)).graph
    # ... and a root that does not release its documents.
    (tree.path / "namespace.nfx").write_text('{"type": "namespace", "released": false}')
    assert nfx_load.previous_document(nb_meta, path, policy, nfx.read(path)).graph
