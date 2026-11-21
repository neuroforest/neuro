"""
Unit tests for neuro.base.labels - `:Label+`, a class with its subclasses.
"""

import pytest

from neuro.base import labels

pytestmark = pytest.mark.unit

TREE = {
    "GitCommit": ["GitCommit", "NfCommit"],
    "GitProject": ["NfProject", "GitProject"],
    "Metadata": ["OntologyMetadata", "Metadata", "KnowledgeMetadata"],
    "Color": ["Color"],
    "n": ["n", "WRONG"],
}


def resolve(label):
    return TREE.get(label, [])


@pytest.mark.parametrize("query, expanded", [
    ("MATCH (c:GitCommit+) RETURN c", "MATCH (c:GitCommit|NfCommit) RETURN c"),
    ("MATCH (p:GitProject+)-[:HAS_COMMIT]->(c:GitCommit+) RETURN p, c",
     "MATCH (p:GitProject|NfProject)-[:HAS_COMMIT]->(c:GitCommit|NfCommit) RETURN p, c"),
    ("MATCH (t:Color+) RETURN t", "MATCH (t:Color) RETURN t"),
    ("MATCH (p:Metadata+ {name: $id}) RETURN p", "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata {name: $id}) RETURN p"),
    ("MATCH (p:`Metadata`+) RETURN p", "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata) RETURN p"),
    ("MATCH (n) WHERE n:Metadata+ AND n.x = 1 RETURN n", "MATCH (n) WHERE n:Metadata|KnowledgeMetadata|OntologyMetadata AND n.x = 1 RETURN n"),
    ("MATCH (n:Metadata+&Node) RETURN n", "MATCH (n:(Metadata|KnowledgeMetadata|OntologyMetadata)&Node) RETURN n"),
    ("MATCH (n:Color+&Node) RETURN n", "MATCH (n:Color&Node) RETURN n"),
    ("MATCH (p:Metadata+) SET p.seen = true", "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata) SET p.seen = true"),
    ("MATCH (p:Metadata+) WITH p MERGE (p)-[:HAS_PROPERTY]->(s:String {label: $t})",
     "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata) WITH p MERGE (p)-[:HAS_PROPERTY]->(s:String {label: $t})"),
    ("RETURN [(a)-->(b:Metadata+) | b.name] AS titles", "RETURN [(a)-->(b:Metadata|KnowledgeMetadata|OntologyMetadata) | b.name] AS titles"),
    ("MATCH (a) WHERE EXISTS { (a)-->(m) WHERE m:Metadata+ } RETURN a",
     "MATCH (a) WHERE EXISTS { (a)-->(m) WHERE m:Metadata|KnowledgeMetadata|OntologyMetadata } RETURN a"),
    ("CALL { MATCH (p:Metadata+) RETURN p } RETURN p", "CALL { MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata) RETURN p } RETURN p"),
])
def test_expand(query, expanded):
    assert labels.expand(query, resolve) == expanded


@pytest.mark.parametrize("query", [
    "MATCH (c:GitCommit) RETURN c",
    "MATCH (n) RETURN {count:n+1} AS m",
    "MATCH (c:GitCommit {k: $a, v:n+1}) RETURN c",
    "MATCH (c) WHERE c.message = 'see :Metadata+ here' RETURN c",
    'MATCH (c) WHERE c.message = "it\'s :Metadata+" RETURN c',
    "MATCH (c) RETURN c // then :Metadata+\n",
    "MATCH (a)-[:SUBCLASS_OF*]->(b) RETURN a.x + b.y",
    "RETURN reduce(s = 0, x IN [1, 2] | s+x) AS total",
    "MATCH (n:Node&Metadata+) RETURN n",  # only a label right after the colon expands
])
def test_expand_untouched(query):
    assert labels.expand(query, resolve) == query


@pytest.mark.parametrize("query, reason", [
    ("MATCH (x:Nope+) RETURN x", "no class 'Nope'"),
    ("MERGE (p:Metadata+ {name: $id})", "in MERGE"),
    ("CREATE (p:Metadata+)", "in CREATE"),
    ("MATCH (p {nid: $n}) SET p:Metadata+", "in SET"),
    ("MATCH (p {nid: $n}) REMOVE p:Metadata+", "in REMOVE"),
    ("MATCH (a)-[r:Metadata+]->(b) RETURN r", "relationship type"),
])
def test_expand_refused(query, reason):
    with pytest.raises(labels.LabelExpansionError, match=reason):
        labels.expand(query, resolve)


def test_has_placeholder():
    assert labels.has_placeholder("MATCH (c:GitCommit+) RETURN c")
    assert not labels.has_placeholder("MATCH (c:GitCommit) RETURN c.a + 1")


def test_neurobase_expand():
    from neuro.base.api import NeuroBase

    calls = []

    class Stub(NeuroBase):
        def __init__(self):
            pass

        def descendant_labels(self, label):
            calls.append(label)
            return resolve(label)

    nb = Stub()
    assert nb.expand("MATCH (p:Metadata+) RETURN p") == "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata) RETURN p"
    assert nb.expand("MATCH (p:Metadata+), (q:Metadata+) RETURN p") == "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata), (q:Metadata|KnowledgeMetadata|OntologyMetadata) RETURN p"
    assert calls == ["Metadata"]
    assert nb.expand("MATCH (p:Metadata) RETURN p") == "MATCH (p:Metadata) RETURN p"
    # only an expanded query silences "label does not exist"
    assert nb._expanded("MATCH (p:Metadata) RETURN p") == ("MATCH (p:Metadata) RETURN p", {})
    assert nb._expanded("MATCH (p:Metadata+) RETURN p") == (
        "MATCH (p:Metadata|KnowledgeMetadata|OntologyMetadata) RETURN p", {"notifications_disabled_classifications": ["UNRECOGNIZED"]})
    nb.forget_labels()
    nb.expand("MATCH (p:Metadata+) RETURN p")
    assert calls == ["Metadata", "Metadata"]
    nb.LABELS_TTL = -1
    nb.expand("MATCH (p:Metadata+) RETURN p")
    assert calls == ["Metadata", "Metadata", "Metadata"]
