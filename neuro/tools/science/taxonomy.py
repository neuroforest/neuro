"""Keeping a base's NCBI taxa in step with NCBI Taxonomy.

A base holds the organisms it has met as ``:NcbiTaxon {id, name, rank}`` nodes
chained child ``-[:IS_CHILD]->`` parent, the whole lineage above each, as they
stood when an importer minted them. NCBI then moves and renames taxa: on 2026-10-27 taxid 729,
*Haemophilus parainfluenzae*, had become *Parahaemophilus parainfluenzae* under
a new genus, and a re-run of the importer had merged the new parent edge beside
the old one. :func:`sync` walks every node **by id** - the one handle a rename
or a move keeps - asks Entrez what each is now, and brings the graph along.

Six kinds of change, each one line of the changelog a run returns:

===========  ===========================================================
``RENAME``   name or rank differ - the node takes NCBI's
``MOVE``     the parent id differs - the one ``IS_CHILD`` edge is *replaced*,
             after the ancestors the new lineage needs are minted (``MINT``)
``MERGE``    the id was folded into another - the node's edges move to the
             surviving node when the base holds it, else the node takes the id
``GONE``     NCBI no longer answers the id - logged every run, never deleted:
             a taxon with a slide or an isolate behind it is the lab's record
``PRUNE``    after the above, a node nothing points at and that points at
             nothing but its chain - an ancestor a move left behind
``REPAIR``   a node found with two parents before any of this: the bug the
             sync exists to make impossible, mended by the ``MOVE`` that follows
===========  ===========================================================

The graph is reached through the small :class:`Graph` port below - one Cypher
implementation, :class:`NeoGraph`, and whatever a test wants - so the decisions
are testable without a Neo4j behind them. A dry run makes the same decisions
and writes nothing; it cannot see which nodes the writes would have orphaned,
so it reports no ``PRUNE``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

#: NCBI's ``root`` (1): never a node. A taxon whose parent is root is a top.
ROOT_IDS = frozenset({"1", "0", ""})
#: The edges a taxon may *leave* by and still be prunable: its own chain and a
#: category anchor. Anything else leaving it - a blob it holds, say - keeps it.
STRUCTURAL = frozenset({"IS_CHILD", "IN_CATEGORY"})


@dataclass
class Taxon:
    """One taxon node as the graph holds it; ``parents`` are the ids of every
    node its ``IS_CHILD`` edges reach - one, in a healthy graph."""

    nid: str
    id: str
    name: str
    rank: str
    parents: list[str] = field(default_factory=list)


@dataclass
class Change:
    kind: str
    tax_id: str | None
    text: str

    def line(self, when: str) -> str:
        return f"{when}  {self.kind:<6}  {self.tax_id or '-':<8}  {self.text}"


class SyncInvariantError(RuntimeError):
    """A taxon has more than one parent after the run - a bug, not a state."""


class EntrezUnavailable(RuntimeError):
    """Entrez answered nothing for a base that holds taxa: an outage, not a
    taxonomy in which every id was withdrawn. The run stops before a single
    ``GONE`` is written."""


class Graph(Protocol):
    def taxa(self) -> list[Taxon]: ...
    def rename(self, nid: str, name: str, rank: str) -> None: ...
    def set_id(self, nid: str, tax_id: str) -> None: ...
    def mint(self, tax_id: str, name: str, rank: str) -> str: ...
    def set_parent(self, nid: str, parent_nid: str) -> None: ...
    def repoint(self, old_nid: str, new_nid: str) -> None: ...
    def orphans(self) -> list[Taxon]: ...
    def delete(self, nid: str) -> None: ...
    def multi_parent(self) -> int: ...


def sync(graph: Graph, fetch: Callable[[list[str]], dict], dry_run: bool = False) -> list[Change]:
    """Bring every ``:NcbiTaxon`` in ``graph`` to what ``fetch`` says it is now.

    ``fetch`` is :func:`neuro.tools.integrations.ncbi.fetch_taxa` or a stand-in
    with its shape. Returns the changes in the order they were applied; raises
    :class:`SyncInvariantError` when a node is left with two parents."""
    from neuro.tools.integrations.ncbi import merged

    changes: list[Change] = []
    taxa = graph.taxa()
    by_id: dict[str, Taxon] = {t.id: t for t in taxa}
    fetched = fetch(list(by_id))
    if by_id and not fetched:
        raise EntrezUnavailable(f"Entrez answered nothing for {len(by_id)} taxa - an outage, not a withdrawal")
    merges = merged(by_id, fetched)

    def write(fn, *args):
        if not dry_run:
            return fn(*args)
        return None

    # Merges first, so a node folded into another is gone before its target
    # is brought up to date below.
    for old, new in merges.items():
        t = by_id.pop(old)
        if new in by_id:
            target = by_id[new]
            write(graph.repoint, t.nid, target.nid)
            changes.append(Change("MERGE", old, f"{t.name} → {target.name} ({new}): edges moved, node removed"))
        else:
            write(graph.set_id, t.nid, new)
            changes.append(Change("MERGE", old, f"{t.name}: now taxid {new}, node kept"))
            t.id = new
            by_id[new] = t

    # Minted this run, by id - a dry run keeps a placeholder nid so later moves
    # can still be reasoned about.
    minted: dict[str, str] = {}

    def ensure(lineage: list[dict]) -> None:
        """Every ancestor of ``lineage`` (root first) that the base lacks, minted
        and chained to its predecessor."""
        prev: Taxon | None = None
        for entry in lineage:
            tax_id = str(entry["TaxId"])
            if tax_id in ROOT_IDS:
                continue
            if tax_id in by_id:
                prev = by_id[tax_id]
                continue
            nid = write(graph.mint, tax_id, entry["ScientificName"], entry["Rank"]) or f"new:{tax_id}"
            node = Taxon(nid, tax_id, entry["ScientificName"], entry["Rank"],
                         [prev.id] if prev else [])
            if prev:
                write(graph.set_parent, nid, prev.nid)
            by_id[tax_id] = node
            minted[tax_id] = nid
            under = f" under {prev.name}" if prev else ""
            changes.append(Change("MINT", tax_id, f"{node.name} ({node.rank}){under}"))
            prev = node

    for t in list(by_id.values()):
        if t.id in minted:
            continue
        record = fetched.get(t.id)
        if record is None:
            changes.append(Change("GONE", t.id, f"{t.name} ({t.rank}): NCBI no longer answers the id"))
            continue
        name, rank = record["ScientificName"], record["Rank"]
        if (name, rank) != (t.name, t.rank):
            write(graph.rename, t.nid, name, rank)
            changes.append(Change("RENAME", t.id, f"{t.name} ({t.rank}) → {name} ({rank})"))
            t.name, t.rank = name, rank
        if len(t.parents) > 1:
            names = ", ".join(by_id[p].name if p in by_id else p for p in t.parents)
            changes.append(Change("REPAIR", t.id, f"{t.name} had {len(t.parents)} parents: {names}"))
        want = str(record.get("ParentTaxId") or "")
        if want in ROOT_IDS:
            continue
        if t.parents == [want]:
            continue
        ensure(record.get("LineageEx") or [])
        if want not in by_id:
            # LineageEx did not reach the parent (an id Entrez answers oddly):
            # nothing to chain to, and a wrong edge is worse than the old one.
            changes.append(Change("GONE", t.id, f"{t.name}: parent {want} not in the lineage NCBI returned"))
            continue
        parent = by_id[want]
        write(graph.set_parent, t.nid, parent.nid)
        was = ", ".join(by_id[p].name if p in by_id else p for p in t.parents) or "-"
        changes.append(Change("MOVE", t.id, f"{t.name}: {was} → {parent.name}"))
        t.parents = [want]

    if not dry_run:
        while True:
            orphans = graph.orphans()
            if not orphans:
                break
            for o in orphans:
                graph.delete(o.nid)
                changes.append(Change("PRUNE", o.id, f"{o.name} ({o.rank}): no child, no isolate, nothing held"))
        if graph.multi_parent():
            raise SyncInvariantError("a taxon still has more than one IS_CHILD parent after the sync")
    return changes


_EDGE = re.compile(r"^[A-Z][A-Z_]*$")


class NeoGraph:
    """The :class:`Graph` port over a :class:`neuro.base.NeuroBase`. Ids are
    integers in the store and strings here, as Entrez spells them."""

    TAXA = (
        "MATCH (t:NcbiTaxon) OPTIONAL MATCH (t)-[:IS_CHILD]->(p:NcbiTaxon) "
        "RETURN t.nid AS nid, toString(t.id) AS id, t.name AS name, t.rank AS rank, "
        "[x IN collect(p.id) WHERE x IS NOT NULL | toString(x)] AS parents ORDER BY t.name"
    )
    RENAME = "MATCH (t:NcbiTaxon {nid: $nid}) SET t.name = $name, t.rank = $rank"
    SET_ID = "MATCH (t:NcbiTaxon {nid: $nid}) SET t.id = toInteger($id)"
    SET_PARENT = (
        "MATCH (c:NcbiTaxon {nid: $nid}) OPTIONAL MATCH (c)-[r:IS_CHILD]->() DELETE r "
        "WITH DISTINCT c MATCH (p:NcbiTaxon {nid: $parent}) MERGE (c)-[:IS_CHILD]->(p)"
    )
    INCOMING = "MATCH (o)-[r]->(t:NcbiTaxon {nid: $nid}) RETURN o.nid AS other, type(r) AS type, properties(r) AS props"
    OUTGOING = ("MATCH (t:NcbiTaxon {nid: $nid})-[r]->(o) WHERE type(r) <> 'IS_CHILD' "
                "RETURN o.nid AS other, type(r) AS type, properties(r) AS props")
    DELETE = "MATCH (t:NcbiTaxon {nid: $nid}) DETACH DELETE t"
    ORPHANS = (
        "MATCH (t:NcbiTaxon) WHERE NOT ()-->(t) "
        "AND NOT EXISTS { (t)-[r]->() WHERE NOT type(r) IN $structural } "
        "RETURN t.nid AS nid, toString(t.id) AS id, t.name AS name, t.rank AS rank"
    )
    MULTI = "MATCH (t:NcbiTaxon)-[:IS_CHILD]->() WITH t, count(*) AS n WHERE n > 1 RETURN count(t) AS n"

    def __init__(self, nb):
        self.nb = nb

    def taxa(self):
        return [Taxon(r["nid"], r["id"], r["name"], r["rank"], r["parents"])
                for r in self.nb.get_data(self.TAXA)]

    def rename(self, nid, name, rank):
        self.nb.run_query(self.RENAME, {"nid": nid, "name": name, "rank": rank})

    def set_id(self, nid, tax_id):
        self.nb.run_query(self.SET_ID, {"nid": nid, "id": tax_id})

    def mint(self, tax_id, name, rank):
        from neuro.core import Node
        node = Node(labels=["NcbiTaxon"], properties={"id": int(tax_id), "name": name, "rank": rank})
        self.nb.nodes.put(node)
        return node.uuid

    def set_parent(self, nid, parent_nid):
        self.nb.run_query(self.SET_PARENT, {"nid": nid, "parent": parent_nid})

    def repoint(self, old_nid, new_nid):
        for row in self.nb.get_data(self.INCOMING, {"nid": old_nid}):
            self._edge(row["other"], new_nid, row["type"], row["props"])
        for row in self.nb.get_data(self.OUTGOING, {"nid": old_nid}):
            self._edge(new_nid, row["other"], row["type"], row["props"])
        self.nb.run_query(self.DELETE, {"nid": old_nid})

    def _edge(self, src, dst, rel_type, props):
        if not _EDGE.match(rel_type):
            raise ValueError(f"not a relationship type: {rel_type!r}")
        self.nb.run_query(
            f"MATCH (a {{nid: $a}}), (b {{nid: $b}}) MERGE (a)-[r:{rel_type}]->(b) SET r += $props",
            {"a": src, "b": dst, "props": props or {}})

    def orphans(self):
        return [Taxon(r["nid"], r["id"], r["name"], r["rank"])
                for r in self.nb.get_data(self.ORPHANS, {"structural": sorted(STRUCTURAL)})]

    def delete(self, nid):
        self.nb.run_query(self.DELETE, {"nid": nid})

    def multi_parent(self):
        rows = self.nb.get_data(self.MULTI)
        return rows[0]["n"] if rows else 0
