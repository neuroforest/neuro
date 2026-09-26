"""
Integration tests for NeuroBase database availability.
"""

import pytest


class TestNeuroBase:
    def test_connectivity(self, nb):
        nb.driver.verify_connectivity()

    def test_count_nodes(self, nb):
        count = nb.count()
        assert isinstance(count, int)


class TestOntology:
    def test_clear_preserves_data_nodes(self, nb_meta):
        """nb.ontology.clear() must not delete non-ontology nodes."""
        nb_meta.run_query("""
            MATCH (o:OntologyNode {label: "OntologyNode"})
            CREATE (d:DataNode {name: "test-data-clear", value: "hello"})
            CREATE (d)-[:LINKED_TO]->(o)
        """)

        assert nb_meta.count("DataNode") == 1
        nb_meta.ontology.clear(confirm=True)
        assert nb_meta.count("OntologyNode") == 0
        assert nb_meta.count("DataNode") == 1
        r = nb_meta.get_data("MATCH (d:DataNode {name: 'test-data-clear'}) RETURN d.value as v")
        assert r[0]["v"] == "hello"


class TestNodeAccessor:
    def test_get_not_found(self, nb):
        """Getting a nonexistent nid raises ValueError."""
        with pytest.raises(ValueError, match="No node found"):
            nb.nodes.get("nonexistent-uuid-000")

    def test_reconcile_internal_edges_is_type_scoped(self, nb):
        """Reconciliation only touches the edge types the file declares.

        Regression: a knowledge file that declares stub nodes purely to be
        `APPLIES_TO` targets (e.g. metrics pointing at a class + its subclasses)
        must not reap the foreign `SUBCLASS_OF` edges among those co-declared
        nodes — a blanket "delete any internal edge not in the file" did, which
        silently broke the ontology's subclass tree on every knowledge import.
        """
        nb.run_query(
            """
            CREATE (parent {nid: 'rc-parent'})
            CREATE (child  {nid: 'rc-child'})
            CREATE (metric {nid: 'rc-metric'})
            CREATE (child)-[:SUBCLASS_OF]->(parent)
            CREATE (metric)-[:APPLIES_TO]->(parent)
            CREATE (metric)-[:APPLIES_TO]->(child)
            """
        )
        nids = ["rc-parent", "rc-child", "rc-metric"]

        def edges():
            rows = nb.get_data(
                "MATCH (a)-[r]->(b) WHERE a.nid IN $nids AND b.nid IN $nids "
                "RETURN a.nid AS f, b.nid AS t, type(r) AS ty",
                {"nids": nids},
            )
            return {(r["f"], r["t"], r["ty"]) for r in rows}

        # The file declares only its APPLIES_TO edges (never SUBCLASS_OF).
        nb.nodes._reconcile_internal_edges(
            nids,
            [("rc-metric", "rc-parent", "APPLIES_TO"),
             ("rc-metric", "rc-child", "APPLIES_TO")],
        )
        assert ("rc-child", "rc-parent", "SUBCLASS_OF") in edges(), \
            "foreign SUBCLASS_OF edge must survive reconciliation"
        assert ("rc-metric", "rc-child", "APPLIES_TO") in edges()

        # Dropping a managed (APPLIES_TO) edge from the file still prunes it,
        # while the untouched foreign type stays put.
        nb.nodes._reconcile_internal_edges(
            nids,
            [("rc-metric", "rc-parent", "APPLIES_TO")],
        )
        assert edges() == {
            ("rc-child", "rc-parent", "SUBCLASS_OF"),
            ("rc-metric", "rc-parent", "APPLIES_TO"),
        }



class TestOntologyExport:
    """`Ontology.export_nfx` writes one valid module per ontology (issue #72)."""

    CORE = "3c1f4a2e-6b7d-4e8f-9a1b-2c3d4e5f6a7b"
    DEP = "4d2e5b3f-7c8e-4f9a-8b2c-3d4e5f6a7b8c"
    CORE_NODE = "5e3f6c4a-8d9f-4a1b-9c3d-4e5f6a7b8c9d"
    DEP_NODE = "6f4a7d5b-9e1a-4b2c-8d4e-5f6a7b8c9d1e"

    NODE = "14a622cd-8c2d-4957-859b-9abe90d38ecc"  # metaontology's `Node` class

    @staticmethod
    def _write(tmp_path, name, nid, version, nodes, relationships=(), dependencies=()):
        from neuro.base import nfx
        path = tmp_path / f"{name}.nfx"
        nfx.write(path, nfx.Nfx.from_dict({
            "type": "ontology", "nid": nid, "version": version, "name": name,
            "dependencies": list(dependencies), "nodes": list(nodes),
            "relationships": list(relationships),
        }))
        return path

    @staticmethod
    def _meta_pin():
        """The metaontology's own `nid@version`, read rather than hardcoded."""
        from neuro.base import nfx
        from neuro.utils.internal_utils import get_path
        meta = nfx.read(get_path("assets") / "ontology" / "metaontology.nfx")
        return f"{meta.nid}@{meta.version}"

    def _core(self, tmp_path):
        """A minimal ontology hanging one class off the metaontology's `Node`."""
        return self._write(
            tmp_path, "core", self.CORE, "1.0",
            [{"nid": self.CORE_NODE, "labels": ["OntologyNode"], "properties": {"label": "Core"}}],
            [{"from": self.CORE_NODE, "to": self.NODE, "type": "SUBCLASS_OF"}],
            [self._meta_pin()],
        )

    def test_export_reproduces_the_metaontology_source(self, nb_meta, tmp_path):
        """The export must reproduce `assets/ontology/metaontology.nfx`.

        This replaces the old `test_nfx_integrity`, which exported through a
        second, bespoke query in `Metaontology` — retired once this path was
        shown to reproduce the same file, since two writers for one document is
        the drift that produced issue #72. `report_repetition` is not optional:
        without it `ignore_order` treats `[a, a, b]` as equal to `[a, b]`, which
        is why the old test passed for as long as that export emitted every
        relationship twice.
        """
        import json

        import deepdiff
        from neuro.base import nfx
        from neuro.utils.internal_utils import get_path

        original = nfx.read(get_path("assets") / "ontology" / "metaontology.nfx")
        out = tmp_path / "Metaontology.nfx"
        doc = nb_meta.ontology.export_nfx(out, name="Metaontology")

        violations = nfx.validate(doc)
        assert violations["missing_required"] == []
        assert violations["duplicate_relationships"] == []
        assert violations["duplicate_nids"] == []
        lint = nfx.lint_format(json.loads(out.read_text()))
        assert lint == {"unknown_keys": [], "key_order": [], "empty": []}, lint

        for field in ("type", "nid", "name", "version", "description"):
            assert getattr(doc, field) == getattr(original, field), field

        node_diff = deepdiff.DeepDiff(list(original.nodes), list(doc.nodes),
                                      ignore_order=True, report_repetition=True)
        assert node_diff == {}, f"Nodes mismatch:\n{node_diff}"

        rel_diff = deepdiff.DeepDiff(list(original.relationships), list(doc.relationships),
                                     ignore_order=True, report_repetition=True)
        assert rel_diff == {}, f"Relationships mismatch:\n{rel_diff}"

    def test_export_is_case_insensitive_and_rejects_unknown(self, nb_meta, tmp_path):
        from neuro.utils import exceptions
        assert nb_meta.ontology.export_nfx(tmp_path / "a.nfx", name="metaONTOLOGY")
        with pytest.raises(exceptions.NoOntology):
            nb_meta.ontology.export_nfx(tmp_path / "b.nfx", name="nope")

    def test_export_without_name_writes_one_file_per_ontology(self, nb_meta, tmp_path):
        nb_meta.metaontology.import_nfx(self._core(tmp_path))
        out = tmp_path / "out"
        docs = nb_meta.ontology.export_nfx(out)
        assert {d.name for d in docs} == {"Metaontology", "core"}
        assert {p.name for p in out.glob("*.nfx")} == {"Metaontology.nfx", "core.nfx"}

    def test_export_assigns_a_cross_module_edge_to_the_dependent(self, nb_meta, tmp_path):
        """An edge out of a dependency's node belongs to the file that can declare it.

        `core` cannot reference `dep`'s node — it does not depend on it — so
        assigning the edge by its source node writes an upward reference into
        `core.nfx`, which then fails to import against its own dependencies.
        """
        from neuro.base import nfx
        nb_meta.metaontology.import_nfx(self._core(tmp_path))
        dep = self._write(
            tmp_path, "dep", self.DEP, "1.0",
            [{"nid": self.DEP_NODE, "labels": ["OntologyRelationship"],
              "properties": {"label": "POINTS_AT"}}],
            # declared here, but its source is core's node
            [{"from": self.CORE_NODE, "to": self.DEP_NODE, "type": "HAS_RELATIONSHIP"}],
            [f"{self.CORE}@1.0"],
        )
        nb_meta.metaontology.import_nfx(dep)

        out = tmp_path / "out"
        by_name = {d.name: d for d in nb_meta.ontology.export_nfx(out)}
        edge = (self.CORE_NODE, self.DEP_NODE, "HAS_RELATIONSHIP")
        assert edge in {(r["from"], r["to"], r["type"]) for r in by_name["dep"].relationships}
        assert edge not in {(r["from"], r["to"], r["type"]) for r in by_name["core"].relationships}
        # and core is importable on its own terms
        core_doc = nfx.read(out / "core.nfx")
        meta_nids = {n["nid"] for n in by_name["Metaontology"].nodes}
        assert nfx.validate(core_doc, meta_nids)["unresolved"] == []

    def test_export_round_trips_the_whole_ontology_layer(self, nb_meta, tmp_path):
        """Clear the layer, rebuild it from the exports, expect the same graph."""
        nodes_q = """
        MATCH (m:OntologyMetadata)-[:DEFINES]->(n)
        RETURN n.nid AS nid, apoc.coll.sort(labels(n)) AS labels, properties(n) AS props
        ORDER BY nid
        """
        edges_q = """
        MATCH (a)-[r]->(b) WHERE a.nid IS NOT NULL AND b.nid IS NOT NULL
          AND NOT a:OntologyMetadata AND NOT b:OntologyMetadata
        RETURN a.nid AS f, b.nid AS t, type(r) AS ty ORDER BY f, t, ty
        """
        out = tmp_path / "out"
        nb_meta.ontology.export_nfx(out)
        before = (nb_meta.get_data(nodes_q), nb_meta.get_data(edges_q))
        nb_meta.ontology.clear(confirm=True)
        assert nb_meta.ontology.count() == 0
        nb_meta.metaontology.import_nfx(out / "Metaontology.nfx")
        assert (nb_meta.get_data(nodes_q), nb_meta.get_data(edges_q)) == before
