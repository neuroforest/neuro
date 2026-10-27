"""The NCBI taxon sync - decisions against a fake graph and a fake Entrez.

The shape of a base on 2026-10-27, when taxid 729 (*Haemophilus parainfluenzae*)
had been moved by NCBI to a new genus *Parahaemophilus* (3705180) and renamed,
and the importer had left it with two parents.
"""
import pytest

from neuro.tools.science import taxonomy
from neuro.tools.science.taxonomy import Taxon


class FakeGraph:
    """The Graph port in memory: nodes by nid, edges as (child, parent) pairs,
    plus the non-chain edges that decide pruning."""

    def __init__(self, taxa, held=()):
        self.nodes = {t.nid: t for t in taxa}
        self.held = set(held)          # nids holding something (a blob, an isolate)
        self.log = []
        self.counter = 0

    def taxa(self):
        return [Taxon(t.nid, t.id, t.name, t.rank, list(t.parents)) for t in self.nodes.values()]

    def rename(self, nid, name, rank):
        self.nodes[nid].name, self.nodes[nid].rank = name, rank
        self.log.append(("rename", nid, name, rank))

    def set_id(self, nid, tax_id):
        self.nodes[nid].id = tax_id
        self.log.append(("set_id", nid, tax_id))

    def mint(self, tax_id, name, rank):
        self.counter += 1
        nid = f"n{self.counter}"
        self.nodes[nid] = Taxon(nid, tax_id, name, rank, [])
        self.log.append(("mint", nid, tax_id))
        return nid

    def set_parent(self, nid, parent_nid):
        self.nodes[nid].parents = [self.nodes[parent_nid].id]
        self.log.append(("set_parent", nid, parent_nid))

    def repoint(self, old_nid, new_nid):
        old = self.nodes.pop(old_nid)
        for t in self.nodes.values():
            t.parents = [new_id if p == old.id else p for p in t.parents
                         for new_id in [self.nodes[new_nid].id]]
        if old_nid in self.held:
            self.held.discard(old_nid)
            self.held.add(new_nid)
        self.log.append(("repoint", old_nid, new_nid))

    def orphans(self):
        parents = {p for t in self.nodes.values() for p in t.parents}
        return [t for t in self.nodes.values() if t.id not in parents and t.nid not in self.held]

    def delete(self, nid):
        del self.nodes[nid]
        self.log.append(("delete", nid))

    def multi_parent(self):
        return sum(1 for t in self.nodes.values() if len(t.parents) > 1)


def rec(tax_id, name, rank, parent, lineage=()):
    return {"TaxId": tax_id, "ScientificName": name, "Rank": rank, "ParentTaxId": parent,
            "AkaTaxIds": [], "LineageEx": [{"TaxId": i, "ScientificName": n, "Rank": r}
                                           for i, n, r in lineage]}


PASTEURELLACEAE = ("712", "Pasteurellaceae", "family")
HAEMOPHILUS = ("724", "Haemophilus", "genus")
PARAHAEMOPHILUS = ("3705180", "Parahaemophilus", "genus")


def graph_2026_10_27():
    return FakeGraph([
        Taxon("fam", "712", "Pasteurellaceae", "family", ["135625"]),
        Taxon("ord", "135625", "Pasteurellales", "order", []),
        Taxon("hae", "724", "Haemophilus", "genus", ["712"]),
        Taxon("hin", "727", "Haemophilus influenzae", "species", ["724"]),
        Taxon("hpa", "729", "Haemophilus parainfluenzae", "species", ["724", "3705180"]),
        Taxon("par", "3705180", "Parahaemophilus", "genus", ["712"]),
    ], held={"hin", "hpa"})


def entrez_now(ids):
    """What Entrez said on 2026-10-27, for the ids asked."""
    world = {
        "712": rec("712", "Pasteurellaceae", "family", "135625"),
        "135625": rec("135625", "Pasteurellales", "order", "1236"),
        "724": rec("724", "Haemophilus", "genus", "712"),
        "727": rec("727", "Haemophilus influenzae", "species", "724"),
        "729": rec("729", "Parahaemophilus parainfluenzae", "species", "3705180",
                   lineage=[PASTEURELLACEAE, PARAHAEMOPHILUS]),
        "3705180": rec("3705180", "Parahaemophilus", "genus", "712"),
    }
    return {i: world[i] for i in ids if i in world}


def kinds(changes):
    return [(c.kind, c.tax_id) for c in changes]


class TestSync:
    def test_rename_and_repair_to_one_parent(self):
        g = graph_2026_10_27()
        changes = taxonomy.sync(g, entrez_now)
        assert ("RENAME", "729") in kinds(changes)
        assert ("REPAIR", "729") in kinds(changes)
        assert ("MOVE", "729") in kinds(changes)
        assert g.nodes["hpa"].parents == ["3705180"]
        assert g.nodes["hpa"].name == "Parahaemophilus parainfluenzae"
        assert g.multi_parent() == 0
        # The order the lab's Pasteurellales sits in points at root-level 1236,
        # which the base does not hold: no lineage was given, so no move.
        assert not any(k == "MOVE" and i == "135625" for k, i in kinds(changes))

    def test_quiet_when_nothing_changed(self):
        g = graph_2026_10_27()
        taxonomy.sync(g, entrez_now)
        again = taxonomy.sync(g, entrez_now)
        assert [c.kind for c in again if c.kind != "GONE"] == []

    def test_move_mints_missing_ancestors(self):
        g = FakeGraph([
            Taxon("fam", "712", "Pasteurellaceae", "family", []),
            Taxon("hae", "724", "Haemophilus", "genus", ["712"]),
            Taxon("hpa", "729", "Haemophilus parainfluenzae", "species", ["724"]),
        ], held={"hpa"})
        changes = taxonomy.sync(g, entrez_now)
        assert ("MINT", "3705180") in kinds(changes)
        minted = next(t for t in g.nodes.values() if t.id == "3705180")
        assert minted.parents == ["712"]
        assert g.nodes["hpa"].parents == ["3705180"]
        # Haemophilus has no species left and holds nothing: pruned.
        assert ("PRUNE", "724") in kinds(changes)
        assert "hae" not in g.nodes

    def test_prune_spares_a_node_that_holds_something(self):
        g = FakeGraph([
            Taxon("fam", "712", "Pasteurellaceae", "family", []),
            Taxon("hae", "724", "Haemophilus", "genus", ["712"]),
            Taxon("hpa", "729", "Haemophilus parainfluenzae", "species", ["724"]),
        ], held={"hpa", "hae"})
        changes = taxonomy.sync(g, entrez_now)
        assert ("PRUNE", "724") not in kinds(changes)

    def test_merge_onto_existing_node_moves_edges(self):
        g = FakeGraph([
            Taxon("gen", "10", "Genus", "genus", []),
            Taxon("a", "11", "Genus alpha", "species", ["10"]),
            Taxon("b", "12", "Genus beta", "species", ["10"]),
            Taxon("sub", "13", "Genus beta subsp.", "subspecies", ["12"]),
        ], held={"a", "b", "sub"})

        def entrez(ids):
            out = {"10": rec("10", "Genus", "genus", "1"),
                   "11": rec("11", "Genus alpha", "species", "10"),
                   "13": rec("13", "Genus alpha subsp.", "subspecies", "11")}
            out["11"]["AkaTaxIds"] = ["12"]      # 12 was merged into 11
            return {i: out[i] for i in ids if i in out}

        changes = taxonomy.sync(g, entrez)
        assert ("MERGE", "12") in kinds(changes)
        assert "b" not in g.nodes
        assert g.nodes["sub"].parents == ["11"]

    def test_merge_into_unknown_id_keeps_the_node(self):
        g = FakeGraph([Taxon("x", "20", "Old name", "species", [])], held={"x"})

        def entrez(ids):
            r = rec("21", "New name", "species", "1")
            r["AkaTaxIds"] = ["20"]
            return {"21": r}

        changes = taxonomy.sync(g, entrez)
        assert kinds(changes)[:2] == [("MERGE", "20"), ("RENAME", "21")]
        assert g.nodes["x"].id == "21" and g.nodes["x"].name == "New name"

    def test_gone_is_logged_not_deleted(self):
        g = graph_2026_10_27()
        g.nodes["x"] = Taxon("x", "99", "Withdrawn", "species", ["724"])
        g.held.add("x")
        changes = taxonomy.sync(g, entrez_now)
        assert ("GONE", "99") in kinds(changes)
        assert "x" in g.nodes and g.nodes["x"].parents == ["724"]

    def test_an_empty_answer_is_an_outage_not_a_withdrawal(self):
        g = FakeGraph([Taxon("x", "99", "Withdrawn", "species", [])], held={"x"})
        with pytest.raises(taxonomy.EntrezUnavailable):
            taxonomy.sync(g, lambda ids: {})
        assert g.log == []

    def test_dry_run_decides_but_writes_nothing(self):
        g = graph_2026_10_27()
        changes = taxonomy.sync(g, entrez_now, dry_run=True)
        assert ("MOVE", "729") in kinds(changes)
        assert g.log == []
        assert g.nodes["hpa"].parents == ["724", "3705180"]

    def test_invariant_violation_raises(self):
        class Stuck(FakeGraph):
            def multi_parent(self):
                return 1

        g = Stuck([Taxon("x", "727", "Haemophilus influenzae", "species", ["724"])], held={"x"})
        with pytest.raises(taxonomy.SyncInvariantError):
            taxonomy.sync(g, entrez_now)

    def test_changelog_line(self):
        line = taxonomy.Change("MOVE", "729", "x: a → b").line("2026-10-27T03:30:12Z")
        assert line == "2026-10-27T03:30:12Z  MOVE    729       x: a → b"


class TestMerged:
    def test_reads_aka_ids(self):
        from neuro.tools.integrations.ncbi import merged
        fetched = {"11": {"AkaTaxIds": ["12", "5"]}, "13": {"AkaTaxIds": []}}
        assert merged(["11", "12", "13"], fetched) == {"12": "11"}
