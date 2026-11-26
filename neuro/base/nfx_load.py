"""
Importing an `.nfx` document into a base, whatever its type.

One function writes a document: `write_document`. What differs between the
kinds - a schema, instance data, the schema of schemas - is carried by a
`Policy`, so the differences are named in one table instead of living in two
writers that drifted apart. `import_document` is the entry point that reads the
`type` and picks the policy; pair it with `PluginIndex.closure`, which says what
to load and in which order.
"""

import dataclasses

from neuro.base import nfx
from neuro.core import Node
from neuro.utils import exceptions


@dataclasses.dataclass(frozen=True)
class Policy:
    """How one kind of document is written.

    anchor: the metadata label the document hangs off.
    shapes: judge every relationship against the loaded ontology first - what
        instance data needs and a schema, which *is* the ontology, cannot have.
    stubs: a node a dependency owns may be re-declared as an edge endpoint, and
        is then left untouched instead of being taken over.
    prune: a node the document stops declaring is deleted with its edges, where
        the other kinds only release it.
    own_tail: only edges leaving a node the document declares are its to
        retract; without it, any edge between two nodes it names is.
    relink_pins: the anchor's `DEPENDS_ON` set is replaced by the document's,
        where the other kinds only ever add to it.
    replace_edges: an edge's properties are replaced by the document's, where
        the other kinds merge into what is there.
    """
    kind: str
    anchor: str
    shapes: bool = False
    stubs: bool = False
    prune: bool = False
    own_tail: bool = True
    relink_pins: bool = False
    replace_edges: bool = False


POLICIES = {
    "ontology": Policy("ontology", "OntologyMetadata"),
    "metaontology": Policy("metaontology", "OntologyMetadata"),
    "knowledge": Policy("knowledge", "KnowledgeMetadata", shapes=True, stubs=True, prune=True,
                        own_tail=False, relink_pins=True, replace_edges=True),
}


def policy_for(doc) -> Policy:
    """The policy of a document's `type`. A typeless document is an ontology,
    as it has always been read."""
    return POLICIES.get(doc.type or "ontology", POLICIES["ontology"])


def import_document(nb, idx, path, on_import=None):
    """Write the document at `path` into `nb` and return its report. Its
    dependencies are expected to be there already - load `idx.closure(path)`
    first, in order.

    `idx` resolves every pin of the document, so it has to see all types (an
    `NfxIndex`). For a knowledge module the nodes its dependencies declare are
    passed on as owned elsewhere: a module that re-declares one as an edge
    endpoint must not take it over from its owner.
    """
    doc = nfx.read(path)
    if doc.type == "knowledge":
        return write_document(nb, path, POLICIES["knowledge"],
                              dependency_nids=idx.dependency_node_nids(path), index=idx)
    return nb.metaontology.import_nfx(path, index=idx, on_import=on_import)


def write_document(nb, path, policy, dependency_nids=None, index=None):
    """Reconcile the document at `path` into `nb` under `policy`.

    The document is anchored on a metadata node (its top-level `nid`), and
    `(anchor)-[:DEFINES]->(node)` records what it declares. Each call adds what
    is new, rewrites what is still declared, drops what is no longer declared
    and retracts the edges it used to carry. Dependencies are not imported
    here; `dependency_nids` is every node nid they declare.

    Returns the import report: `nodes`, `released`, `reparented`, `orphaned`,
    `edges_pruned`. `index`, when given, is where the document's tree is looked
    up: its namespace token is recorded on the anchor, since a module's name is
    unique inside its tree only.
    """
    doc = nfx.read(path)

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

    declared = list(doc.node_nids)
    report = {"nodes": len(declared), "released": [], "reparented": [],
              "orphaned": [], "edges_pruned": 0}
    meta = nb.metadata

    if policy.prune:
        meta.prune(policy.anchor, doc.nid, declared)
    else:
        report.update(nb.metaontology._release_undeclared(doc.nid, declared))

    properties = {k: v for k, v in (
        ("name", doc.name), ("version", doc.version),
        ("description", doc.description), ("type", doc.type),
    ) if v}
    pins = [dep_nid for dep_nid, _ in doc.dependencies]
    if policy.relink_pins:
        meta.upsert(policy.anchor, doc.nid, properties, dependency_nids=pins)
    else:
        meta.upsert_additive(policy.anchor, doc.nid, properties, dependency_nids=pins)
    # Only an index knows which tree the file belongs to; without one the
    # namespace already recorded stays as it is.
    if index is not None:
        meta.set_namespace(policy.anchor, doc.nid, index.namespace_for(doc.nid))

    if policy.stubs:
        _write_instance_nodes(nb, doc, policy, set(dependency_nids or ()))
    else:
        _write_schema_nodes(nb, doc, policy)

    keep = [(r["from"], r["to"], r["type"]) for r in doc.relationships]
    if policy.own_tail:
        # Confined to the nids this document touches and to edges leaving its
        # own nodes, so other documents' edges are never candidates.
        scope = set(declared) | {nid for triple in keep for nid in triple[:2]}
        report["edges_pruned"] = nb.nodes._reconcile_internal_edges(scope, keep, sources=declared)
    else:
        report["edges_pruned"] = nb.nodes._reconcile_internal_edges(declared, keep)

    for rel in doc.relationships:
        _write_edge(nb, rel, policy)

    return report


def _write_schema_nodes(nb, doc, policy):
    """Write the nodes of a schema: the document is authoritative for each
    node's properties and labels, and every one is DEFINES-linked.

    A node this document already defines is written through its element id,
    which is what makes a relabel a relabel - see `Metaontology._claimed_nodes`.
    """
    claimed = nb.metaontology._claimed_nodes(doc.nid)
    for entry in doc.nodes:
        labels = entry["labels"]
        params = {"nid": entry["nid"], "props": entry.get("properties", {}), "labels": labels}
        eid = claimed.get(entry["nid"])
        if eid:
            params["eid"] = eid
            anchor = "MATCH (n) WHERE elementId(n) = $eid"
        else:
            anchor = f"MERGE (n:{labels[0]} {{nid: $nid}})"
        # `SET n =` (not `+=`): a property dropped from the file must go, and a
        # label it stopped declaring is removed rather than left to accumulate.
        # Both clauses take the label list as a *parameter* (Neo4j 5.26 dynamic
        # labels), which also keeps a label out of the interpolated query text.
        nb.run_query(
            f"""
            {anchor}
            SET n = $props, n.nid = $nid
            SET n:$($labels)
            WITH n, [l IN labels(n) WHERE NOT l IN $labels] AS stale
            REMOVE n:$(stale)
            """,
            params,
        )
        nb.run_query(
            f"""
            MATCH (m:{policy.anchor} {{nid: $meta_nid}})
            MATCH (n:{labels[0]} {{nid: $node_nid}})
            MERGE (m)-[:DEFINES]->(n)
            """,
            {"meta_nid": doc.nid, "node_nid": entry["nid"]},
        )


def _write_instance_nodes(nb, doc, policy, foreign):
    """Write the nodes of instance data, validated against the ontology.

    A node whose nid belongs to a dependency is a *foreign reference* - the
    document re-declares it only so its own edges have a resolvable endpoint
    (and so it validates standalone). Its properties are the owner's: replacing
    them would strip whatever this document omits (the `color` an OntologyNode
    class carries), and a `DEFINES` would make this anchor co-own it and later
    drop it. So it is left untouched; edge retraction still sees it, since it
    stays in the document's nid set.
    """
    for entry in doc.nodes:
        if entry["nid"] in foreign:
            continue
        properties = dict(entry.get("properties", {}))
        properties["nid"] = entry["nid"]
        node = Node(labels=entry["labels"], properties=properties)
        nb.objects.put(node, identifier_key="nid", replace=True)
        nb.metadata.link_defines(policy.anchor, doc.nid, entry["nid"])


def _write_edge(nb, rel, policy):
    """MERGE one declared relationship and set its properties."""
    if policy.replace_edges:
        ends = "MATCH (a {nid: $from_id})\nMATCH (b {nid: $to_id})"
        assign = "="
    else:
        # Both ends have to be nodes some document of this kind defines.
        ends = (f"MATCH (:{policy.anchor})-[:DEFINES]->(a {{nid: $from_id}})\n"
                f"MATCH (:{policy.anchor})-[:DEFINES]->(b {{nid: $to_id}})")
        assign = "+="
    nb.run_query(
        f"""
        {ends}
        MERGE (a)-[r:{rel["type"]}]->(b)
        SET r {assign} $props
        """,
        {"from_id": rel["from"], "to_id": rel["to"], "props": rel.get("properties", {})},
    )
