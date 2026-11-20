"""
Unit tests for neuro.base.nf_events - the rename and move commit subjects.
"""

import json
import subprocess
import uuid

import pytest

from neuro.base import nf_events

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("subject, event", [
    ("REFACTOR: ontology old-name → new", nf_events.Rename("ontology", "old-name", "new")),
    ("MIGRATE: knowledge stains → micro", nf_events.Departure("knowledge", "stains", "micro")),
    ("MIGRATE: knowledge stains → root", nf_events.Departure("knowledge", "stains", "")),
    ("MIGRATE: knowledge stains ← root", nf_events.Arrival("knowledge", "stains", "")),
    ("MIGRATE: ontology b-cards ← root as a-cards",
     nf_events.Arrival("ontology", "b-cards", "", "a-cards")),
])
def test_parse(subject, event):
    assert nf_events.parse(subject) == event
    assert event.subject == subject
    assert nf_events.parse(subject + "\n\nbody") == event


@pytest.mark.parametrize("subject", [
    "REFACTOR: task ontology.rehash",
    "REFACTOR: ontology a → a",
    "REFACTOR: ontology Old → new",
    "MIGRATE: plugin x → y",
    "MIGRATE: knowledge stains -> micro",
    "MIGRATE: knowledge stains → micro extra",
    "RELEASE: ontology stains 1.2",
    "",
])
def test_parse_other(subject):
    assert nf_events.parse(subject) is None


def test_parse_all():
    message = ("MIGRATE: ontology p ← root\n\nMIGRATE: ontology p ← root · released in root as ontology/p/1.0\n"
               "MIGRATE: ontology a ← root · never released in root\nnot an event\n")
    assert nf_events.parse_all(message) == [nf_events.Arrival("ontology", "p", ""),
                                            nf_events.Arrival("ontology", "a", "")]
    assert nf_events.parse_all("FIX: x") == []


def test_event():
    arrival = nf_events.Arrival("ontology", "a", "", "a")
    assert arrival.subject == "MIGRATE: ontology a ← root"
    assert nf_events.Arrival("ontology", "a", "x", "b").path == "ontology/b.nfx"
    for bad in (lambda: nf_events.Rename("ontology", "A", "b"),
                lambda: nf_events.Departure("ontology", "a", "root"),
                lambda: nf_events.Departure("ontology", "a", "Bad"),
                lambda: nf_events.Arrival("namespace", "a", "")):
        with pytest.raises(ValueError):
            bad()


def _commit(repo, message, files=(), remove=()):
    for rel, doc in files:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))
        subprocess.run(["git", "-C", repo, "add", rel], check=True)
    for rel in remove:
        subprocess.run(["git", "-C", repo, "rm", "-q", rel], check=True)
    subprocess.run(["git", "-C", repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", message], check=True)
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def test_departure_of(tmp_path):
    repo = tmp_path / "src"
    subprocess.run(["git", "init", "-q", repo], check=True)
    nid, other = str(uuid.uuid4()), str(uuid.uuid4())
    rel = ".nf/knowledge/stains.nfx"
    _commit(repo, "ADD: stains", [(rel, {"nid": other})])
    _commit(repo, "MIGRATE: knowledge stains → micro", remove=[rel])
    _commit(repo, "ADD: stains", [(rel, {"nid": nid})])
    sha = _commit(repo, "MIGRATE: knowledge stains → micro", remove=[rel])
    arrival = nf_events.Arrival("knowledge", "stains", "", "dyes")
    assert nf_events.departure_of(repo, ".nf", arrival, nid, "micro") == sha
    assert nf_events.departure_of(repo, ".nf", arrival, nid, "elsewhere") is None
    assert nf_events.departure_of(repo, ".nf", arrival, str(uuid.uuid4()), "micro") is None
    assert nf_events.nid_at(repo, f"{sha}^", rel) == nid
    assert nf_events.nid_at(repo, sha, rel) is None
