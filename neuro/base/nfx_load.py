"""
Importing an `.nfx` document into a base, whatever its type.

One function writes a document: `write_document`. What differs between the
kinds - a schema, instance data, the schema of schemas - is carried by a
`Policy`, so the differences are named in one table instead of living in two
writers that drifted apart. `import_document` is the entry point that reads the
`type` and picks the policy; pair it with `PluginIndex.closure`, which says what
to load and in which order.

What an import takes away is decided by the document's *previous version*, never
by what the base happens to hold beside it:

- a node the document stops declaring is **released** - it loses this
  document's `DEFINES` and nothing else. It is deleted only when nothing is left
  on it; while an edge, or an instance of the class, still reaches it, it stays
  and is reported;
- an edge, a label or a property key is **retracted** when the previous version
  declared it and this one does not. One nobody declared - set by hand, by a
  collector - is not the document's to remove.

The previous version is read from the release tags of the document's `.nf`
root (`nf_repo`). Two cases have no release history and take the base itself as
the previous version, the document then being authoritative for what its anchor
defines: the metaontology, which ships with the app, and a document in no
repository at all.
"""

import dataclasses
import json
from pathlib import Path

from neuro.base import nfx, plugins
from neuro.core import Node
from neuro.utils import exceptions

ANCHORS = "OntologyMetadata|KnowledgeMetadata"


@dataclasses.dataclass(frozen=True)
class Policy:
    """How one kind of document is written.

    anchor: the metadata label the document hangs off.
    shapes: judge every relationship against the loaded ontology first - what
        instance data needs and a schema, which *is* the ontology, cannot have.
    stubs: a node a dependency owns may be re-declared as an edge endpoint, and
        is then left untouched instead of being taken over.
    defined_ends: an edge is written only between nodes some document of this
        kind defines.
    own_tail: with the base as the previous version, only edges leaving a node
        the document declares are its to retract; without it, any edge between
        two nodes it names is.
    graph_previous: the base is always the previous version - a kind that has
        no release history where it is installed.
    """
    kind: str
    anchor: str
    shapes: bool = False
    stubs: bool = False
    defined_ends: bool = False
    own_tail: bool = True
    graph_previous: bool = False


POLICIES = {
    "ontology": Policy("ontology", "OntologyMetadata", defined_ends=True),
    "metaontology": Policy("metaontology", "OntologyMetadata", defined_ends=True, graph_previous=True),
    "knowledge": Policy("knowledge", "KnowledgeMetadata", shapes=True, stubs=True, own_tail=False),
}


def policy_for(doc) -> Policy:
    """The policy of a document's `type`. A typeless document is an ontology,
    as it has always been read."""
    return POLICIES.get(doc.type or "ontology", POLICIES["ontology"])


@dataclasses.dataclass(frozen=True)
class Previous:
    """What the document declared before this import.

    graph: the base stands in for it - the document is authoritative for what
        its anchor defines. Otherwise `doc` is the previous version as released,
        or None when nothing is to be retracted (a first import, or a re-import
        of the version already loaded).
    """
    graph: bool = False
    doc: nfx.Nfx | None = None


def import_document(nb, idx, path, on_import=None):
    """Write the document at `path` into `nb` and return its report. Its
    dependencies are expected to be there already - load `idx.closure(path)`
    first, in order.

    `idx` resolves every pin of the document, so it has to see all types (an
    `NfxIndex`). For a knowledge module the nodes its dependencies declare are
    passed on as owned elsewhere: a module that re-declares one - as an edge
    endpoint, or to add a label and properties to it - must not take it over
    from its owner.
    """
    doc = nfx.read(path)
    if doc.type == "knowledge":
        return write_document(nb, path, POLICIES["knowledge"],
                              dependency_nodes=idx.dependency_nodes(path), index=idx)
    return nb.metaontology.import_nfx(path, index=idx, on_import=on_import)


def release_root(path):
    """`(Repo, root-relative path)` of the git-tracked `.nf` root holding
    `path` and releasing its documents; `(None, None)` for a document in no
    such root. A root whose declaration says `"released": false` (test
    fixtures) commits without tagging, so it has no release history either."""
    from neuro.base import nf_repo
    path = Path(path).resolve()
    root = next((p for p in path.parents if plugins.is_consolidated(p)), None)
    if root is None:
        return None, None
    try:
        if json.loads((root / nfx.NAMESPACE_FILENAME).read_text()).get("released") is False:
            return None, None
    except (OSError, ValueError, AttributeError):
        pass
    try:
        return nf_repo.Repo(root), path.relative_to(root)
    except (RuntimeError, ValueError):
        return None, None


def previous_document(nb, path, policy, doc) -> Previous:
    """What `doc` declared in the version `nb` holds.

    Raises `NfxViolation` when the document lives in a git-tracked root, the
    base holds another version of it, and that version has no readable release
    tag: retracting against a guess would delete what nobody dropped, and
    retracting nothing would leave what somebody did.
    """
    from neuro.base import nf_repo
    rows = nb.get_data(
        f"MATCH (m:{policy.anchor} {{nid: $nid}}) RETURN m.version AS version", {"nid": doc.nid},
    )
    if not rows:
        return Previous()
    if policy.graph_previous:
        return Previous(graph=True)
    repo, rel = release_root(path)
    if repo is None:
        return Previous(graph=True)
    loaded = rows[0]["version"] or ""
    series = nf_repo.series_of(rel)
    tag = repo.tag_of(series, loaded) if series and loaded else None
    data = repo.doc_at(tag, rel) if tag else None
    if data is not None and data.get("nid") == doc.nid:
        return Previous(doc=nfx.Nfx.from_dict(data))
    if loaded == doc.version:
        return Previous()  # no release lies between
    raise exceptions.NfxViolation(
        f"{path}: the base holds {doc.name} {loaded or '(no version)'} and its release "
        f"{tag or 'tag'} cannot be read from {repo.top} - without it nothing says what "
        f"{doc.version} dropped. Refusing to import."
    )


def write_document(nb, path, policy, dependency_nids=None, index=None, dependency_nodes=None):
    """Reconcile the document at `path` into `nb` under `policy`.

    The document is anchored on a metadata node (its top-level `nid`), and
    `(anchor)-[:DEFINES]->(node)` records what it declares. Dependencies are
    not imported here; `dependency_nids` is every node nid they declare.
    `dependency_nodes` (`NfxTree.dependency_nodes()`) says the same and what
    they declare of each node, which is what lets a document *extend* a
    dependency's node: without it a re-declared node is an endpoint only.

    Returns the import report: `nodes`, `extended` (nodes of a dependency this
    document adds to), and what left - `released` (every node dropped),
    `reparented` (another document defines it now), `removed` (nothing was
    left on it, so it is gone), `orphaned` (kept, with the number of edges,
    instances, labels and properties holding it) and `edges_pruned`. `index`,
    when given, is where the document's tree is looked up: its namespace token
    is recorded on the anchor, since a module's name is unique inside its tree
    only.
    """
    doc = nfx.read(path)
    if dependency_nodes is not None:
        dependency_nids = set(dependency_nodes)

    # `nid` and `name` are what the anchor is built from, and every edge below
    # is written between nodes some anchor DEFINES. A document missing either
    # would import its nodes, anchor none of them, and lose its structure with
    # a clean exit status.
    missing = [f for f in ("nid", "name") if not getattr(doc, f)]
    if missing:
        raise exceptions.NfxViolation(
            f"{path} declares no {', '.join(repr(f) for f in missing)} - without it no "
            f"{policy.anchor} is minted, so no node would be DEFINES'd and all "
            f"{len(doc.relationships)} relationship(s) would be dropped. Refusing to import."
        )

    nb.nodes._validate_structure(doc, path, dependency_nids)
    if policy.shapes:
        nb.nodes._validate_relationship_shapes(doc, path)
    extended = _extensions(nb, doc, path, dependency_nodes) if policy.stubs else {}
    # Before the first write: a refusal leaves the base as it was.
    previous = previous_document(nb, path, policy, doc)

    declared = list(doc.node_nids)
    released = _release(nb, policy, doc.nid, declared)

    properties = {k: v for k, v in (
        ("name", doc.name), ("version", doc.version),
        ("description", doc.description), ("type", doc.type),
    ) if v}
    nb.metadata.upsert(policy.anchor, doc.nid, properties,
                       dependency_nids=[dep_nid for dep_nid, _ in doc.dependencies])
    # Only an index knows which tree the file belongs to; without one the
    # namespace already recorded stays as it is.
    if index is not None:
        nb.metadata.set_namespace(policy.anchor, doc.nid, index.namespace_for(doc.nid))

    before = {n["nid"]: n for n in previous.doc.nodes} if previous.doc else {}
    foreign = set(dependency_nids or ()) if policy.stubs else set()
    claimed = {} if policy.stubs else nb.metaontology._claimed_nodes(doc.nid)
    for entry in doc.nodes:
        if entry["nid"] in foreign:
            # A *foreign reference*: re-declared so this document's own edges
            # have an endpoint, or to add to it (`_extend`). What its owner
            # says of it is the owner's, and a `DEFINES` would make this
            # anchor co-own it and later drop it.
            continue
        _write_node(nb, doc, policy, entry, previous, before.get(entry["nid"]), claimed)
    if policy.stubs and dependency_nodes:
        _extend(nb, extended, previous, dependency_nodes)

    pruned = _retract_edges(nb, doc, policy, previous, declared)
    _write_edges(nb, doc, policy, previous)

    removed, orphaned = _split(nb, [r for r in released if not r["claimed_by"]], previous)
    return {
        "nodes": len(declared),
        "extended": len(extended),
        "released": [r["label"] for r in released],
        "reparented": [(r["label"], r["claimed_by"]) for r in released if r["claimed_by"]],
        "removed": removed,
        "orphaned": orphaned,
        "edges_pruned": pruned,
    }


def _extensions(nb, doc, path, dependency_nodes):
    """What `doc` adds to its dependencies' nodes (`nfx.extensions`), refused
    when it sets a key a dependency sets otherwise, extends a node no knowledge
    module declares, or leaves a node the ontology does not accept. The node
    judged is the sum of what its declaring modules say of it - what the base
    holds beside that was never validated and is not this document's to
    answer for."""
    from neuro.base.ontology import ObjectValidator
    extended, issues = nfx.extensions(doc, dependency_nodes or {})
    for nid, added in extended.items():
        declared = added["declared"]
        violations = ObjectValidator(nb, Node(
            labels=[*declared["labels"], *added["labels"]],
            properties={**declared["properties"], **added["properties"], "nid": nid},
        )).get_violations()
        if violations:
            issues.append(f"{nid}: {violations}")
    if issues:
        raise exceptions.NfxViolation(
            f"{path} extends a node of a dependency and cannot:\n" + "\n".join(f"  {i}" for i in issues)
        )
    return extended


def _extend(nb, extended, previous, dependency_nodes):
    """Write this document's contribution to the nodes it extends, and take
    back what its previous version contributed and this one does not. The
    owner's part is never touched: a contribution is by construction what no
    dependency declares."""
    before = nfx.extensions(previous.doc, dependency_nodes)[0] if previous.doc else {}
    for nid in sorted(set(extended) | set(before)):
        now, was = extended.get(nid), before.get(nid)
        labels = now["labels"] if now else []
        properties = now["properties"] if now else {}
        dropped_labels = sorted(set(was["labels"]) - set(labels)) if was else []
        dropped_keys = sorted(set(was["properties"]) - set(properties)) if was else []
        nb.run_query(
            f"""
            MATCH (n:{_quoted((now or was)["declared"]["labels"][0])} {{nid: $nid}})
            SET n += $props
            SET n += $gone
            SET n:$($labels)
            REMOVE n:$($dropped)
            """,
            {"nid": nid, "props": properties, "gone": dict.fromkeys(dropped_keys),
             "labels": labels, "dropped": dropped_labels},
        )


def _release(nb, policy, nid, declared):
    """Drop this document's `DEFINES` from the nodes it no longer declares, and
    say what they are. The nodes themselves are kept: the set of edges reaching
    a declared node is open - measured components, metric values and records
    point at it from outside any document - so deleting it here would sever
    edges no import will ever restore. `_split` decides what happens next.

    Each row carries `own`: the nids this anchor defined going in, which is the
    document's slice of the base when the base is the previous version.
    """
    return nb.get_data(
        f"""
        MATCH (m:{policy.anchor} {{nid: $nid}})-[:DEFINES]->(s)
        WITH m, collect(s.nid) AS own
        MATCH (m)-[d:DEFINES]->(n)
        WHERE NOT n.nid IN $declared
        OPTIONAL MATCH (other:{ANCHORS})-[:DEFINES]->(n)
        WHERE other.nid <> $nid
        WITH n, d, own, collect(DISTINCT other.name) AS claimed_by
        DELETE d
        RETURN elementId(n) AS eid, n.nid AS nid,
               coalesce(n.label, n.name, labels(n)[0] + ' ' + n.nid) AS label,
               n.label AS class_label, 'OntologyNode' IN labels(n) AS is_class,
               labels(n) AS labels, keys(n) AS keys, claimed_by, own
        """,
        {"nid": nid, "declared": list(declared)},
    )


def _split(nb, orphans, previous):
    """Delete the released nodes nothing reaches any more; report the rest.

    A node is held by an edge to anything but an anchor - and, where the base
    is the previous version, to anything outside the document's own slice,
    since nothing there says which of its edges the document once declared. A
    class is also held by its instances: they carry it as a *label* and hold no
    edge back to it, so the edge test alone would call a class with ten
    thousand instances isolated. A twin - another defined class of the same
    label - goes on defining them, and then they do not hold this one.

    Against a released previous version a node is held, too, by every label
    and property that version did not declare on it: another module's
    extension, or state set by hand - not this document's to delete with it.

    Returns `(removed, orphaned)`: labels, and `(label, holders)` pairs.
    """
    if not orphans:
        return [], []
    before = {n["nid"]: n for n in previous.doc.nodes} if previous.doc else {}
    own = orphans[0]["own"] if previous.graph else []
    held = {r["eid"]: r["edges"] for r in nb.get_data(
        f"""
        MATCH (n) WHERE elementId(n) IN $eids
        OPTIONAL MATCH (n)-[r]-(o)
        WHERE NOT (o:{ANCHORS}) AND NOT coalesce(o.nid, '') IN $own
        RETURN elementId(n) AS eid, count(r) AS edges
        """,
        {"eids": [r["eid"] for r in orphans], "own": own},
    )}
    removed, orphaned, doomed = [], [], []
    for row in orphans:
        holders = held.get(row["eid"], 0)
        was = before.get(row["nid"])
        if was is not None:
            holders += len(set(row["labels"]) - set(was["labels"]))
            holders += len(set(row["keys"]) - set(was.get("properties", {})) - {"nid"})
        if not holders and row["is_class"] and row["class_label"]:
            holders = _instances(nb, row["class_label"])
        if holders:
            orphaned.append((row["label"], holders))
        else:
            removed.append(row["label"])
            doomed.append(row["eid"])
    if doomed:
        nb.run_query("MATCH (n) WHERE elementId(n) IN $eids DETACH DELETE n", {"eids": doomed})
    return removed, orphaned


def _instances(nb, label):
    """How many instances still need the class `label` - none while another
    defined class of that label exists."""
    twins = nb.get_data(
        "MATCH (:OntologyMetadata)-[:DEFINES]->(t:OntologyNode {label: $label}) RETURN count(t) AS c",
        {"label": label},
    )
    if twins[0]["c"]:
        return 0
    rows = nb.get_data(
        f"""
        MATCH (i:{_quoted(label)})
        WHERE NOT i:OntologyMetadata AND NOT (i)<-[:DEFINES]-(:OntologyMetadata)
        RETURN count(i) AS c
        """
    )
    return rows[0]["c"]


def _quoted(name):
    return "`" + str(name).replace("`", "``") + "`"


def _write_node(nb, doc, policy, entry, previous, before, claimed):
    """Write one declared node and link it to the anchor.

    With the base as the previous version the document is authoritative: its
    properties replace the node's and a label it does not carry is removed.
    Otherwise it adds what it declares and takes back only what its previous
    version declared and this one does not (`before` is that version's entry).
    """
    labels = list(entry["labels"])
    properties = dict(entry.get("properties", {}))
    properties["nid"] = entry["nid"]
    dropped_labels, dropped_keys = [], []
    if before is not None:
        dropped_labels = sorted(set(before["labels"]) - set(labels))
        dropped_keys = sorted(set(before.get("properties", {})) - set(properties))

    if policy.stubs:
        # Instance data: validated against the ontology on the way in.
        nb.objects.put(Node(labels=labels, properties=properties), identifier_key="nid",
                       replace=previous.graph)
        if dropped_labels or dropped_keys:
            nb.run_query(
                f"""
                MATCH (n:{_quoted(labels[0])} {{nid: $nid}})
                SET n += $gone
                REMOVE n:$($dropped)
                """,
                {"nid": entry["nid"], "gone": dict.fromkeys(dropped_keys), "dropped": dropped_labels},
            )
    else:
        # A node this document already defines is written through its element
        # id, which is what makes a relabel a relabel: a label-scoped MERGE
        # stops matching once the labels change, and then creates.
        params = {"nid": entry["nid"], "props": properties, "labels": labels,
                  "gone": dict.fromkeys(dropped_keys), "dropped": dropped_labels}
        eid = claimed.get(entry["nid"])
        if eid:
            params["eid"] = eid
            anchor = "MATCH (n) WHERE elementId(n) = $eid"
        else:
            anchor = f"MERGE (n:{_quoted(labels[0])} {{nid: $nid}})"
        if previous.graph:
            reconcile = """SET n = $props
                SET n:$($labels)
                WITH n, [l IN labels(n) WHERE NOT l IN $labels] AS stale
                REMOVE n:$(stale)"""
        else:
            reconcile = """SET n += $props
                SET n += $gone
                SET n:$($labels)
                REMOVE n:$($dropped)"""
        # The label lists are *parameters* (Neo4j 5.26 dynamic labels), which
        # keeps a label out of the interpolated query text.
        nb.run_query(
            f"""
            {anchor}
            {reconcile}
            """,
            params,
        )
    nb.metadata.link_defines(policy.anchor, doc.nid, entry["nid"], node_label=labels[0])


def _triples(document):
    return {(r["from"], r["to"], r["type"]): r for r in document.relationships}


def _end(var, nid, labels):
    """A node pattern by nid, label-scoped where the label is known - an
    unlabelled lookup scans the base."""
    label = labels.get(nid)
    return f"({var}:{_quoted(label)} {{nid: ${var}}})" if label else f"({var} {{nid: ${var}}})"


def _retract_edges(nb, doc, policy, previous, declared):
    """Delete the edges this document used to carry and no longer does; return
    how many.

    Against a released previous version that is an exact set: the triples it
    declared minus the ones declared now. Against the base it is the slice:
    edges of a type the document declares, between the nodes it touches, that
    it does not carry - and under `own_tail` only those leaving its own nodes,
    so another document's edges between nodes this one merely names are never
    candidates.
    """
    keep = list(_triples(doc))
    if previous.graph:
        if policy.own_tail:
            scope = set(declared) | {nid for triple in keep for nid in triple[:2]}
            return nb.nodes._reconcile_internal_edges(scope, keep, sources=declared)
        return nb.nodes._reconcile_internal_edges(declared, keep)
    if previous.doc is None:
        return 0
    # A dropped node still carries its old first label; a kept one may have
    # changed it, and was rewritten just now.
    labels = {n["nid"]: n["labels"][0] for n in (*previous.doc.nodes, *doc.nodes) if n.get("labels")}
    pruned = 0
    for from_nid, to_nid, rel_type in sorted(set(_triples(previous.doc)) - set(keep)):
        rows = nb.get_data(
            f"""
            MATCH {_end("a", from_nid, labels)}-[r:{_quoted(rel_type)}]->{_end("b", to_nid, labels)}
            DELETE r
            RETURN count(r) AS pruned
            """,
            {"a": from_nid, "b": to_nid},
        )
        pruned += rows[0]["pruned"] if rows else 0
    return pruned


def _write_edges(nb, doc, policy, previous):
    """MERGE every declared relationship and set its properties: replaced when
    the base is the previous version, otherwise merged, minus the keys the
    previous version set on that edge and this one does not."""
    before = _triples(previous.doc) if previous.doc else {}
    if policy.defined_ends:
        # Both ends have to be nodes some document of this kind defines.
        ends = (f"MATCH (:{policy.anchor})-[:DEFINES]->(a {{nid: $from_id}})\n"
                f"MATCH (:{policy.anchor})-[:DEFINES]->(b {{nid: $to_id}})")
    else:
        ends = "MATCH (a {nid: $from_id})\nMATCH (b {nid: $to_id})"
    assign = "SET r = $props" if previous.graph else "SET r += $props\nSET r += $gone"
    for triple, rel in _triples(doc).items():
        properties = rel.get("properties", {})
        gone = set(before.get(triple, {}).get("properties", {})) - set(properties)
        nb.run_query(
            f"""
            {ends}
            MERGE (a)-[r:{rel["type"]}]->(b)
            {assign}
            """,
            {"from_id": rel["from"], "to_id": rel["to"], "props": properties,
             "gone": dict.fromkeys(sorted(gone))},
        )
