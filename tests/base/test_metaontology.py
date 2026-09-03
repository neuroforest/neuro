"""
Integration tests for neuro.base.metaontology
"""

import pytest

from neuro.utils import exceptions


class TestImport:
    def test_import(self):
        from neuro.base.metaontology import Metaontology  # noqa: F401


class TestMetaontology:
    def test_accessor(self, nb):
        assert nb.metaontology is not None

    def test_metaproperties(self, nb_meta):
        from neuro.base.schema import Metaproperties
        mp = Metaproperties.from_ontology(nb_meta, "Node")
        assert "nid" in mp
        assert mp["nid"].is_required()
        assert "color" in mp
        assert mp["color"].property_type == "Color"
        assert not mp["color"].is_required()

    def test_metaontology(self, nb_meta):
        result = nb_meta.metaontology.is_ontology_valid()
        if not result:
            print(nb_meta.metaontology.violations)
        assert result


class TestOntologyValidator:
    def test_no_ontology_raises(self, nb):
        with pytest.raises(exceptions.NoOntology):
            nb.metaontology.is_ontology_valid()

    def test_disconnected_ontology(self, nb_meta):
        nb_meta.run_query("CREATE (:OntologyNode {label: 'Orphan', nid: randomUUID()})")
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert violations.disconnected
        violations.disconnected = False
        assert not violations

    def test_undefined_property(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'HasBogus', nid: randomUUID(), bogus: 'x'})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("HasBogus", "OntologyNode")
        assert "bogus" in v.undefined_properties
        violations.violations.clear()
        assert not violations

    def test_invalid_label(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'bad-label', nid: randomUUID()})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("bad-label", "OntologyNode")
        assert "label" in [p for p, _ in v.invalid_properties]
        violations.violations.clear()
        assert not violations

    def test_invalid_nid(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'BadId', nid: 'not-a-uuid-v4'})"
            "-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("BadId", "OntologyNode")
        assert "nid" in [p for p, _ in v.invalid_properties]
        violations.violations.clear()
        assert not violations

    def test_missing_property(self, nb_meta):
        nb_meta.run_query(
            "MATCH (root:OntologyNode {label: 'Node'})"
            "CREATE (n:OntologyNode {label: 'NoId'})-[:SUBCLASS_OF]->(root)"
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        violations = nb_meta.metaontology.violations
        assert len(violations.violations) == 1
        label, ontology_object_type, v = violations.violations[0]
        assert (label, ontology_object_type) == ("NoId", "OntologyNode")
        assert "nid" in [p.label for p in v.missing_properties]
        violations.violations.clear()
        assert not violations


class TestPropertyOverrides:
    """Property name conflicts across SUBCLASS_OF lineage.

    Each test scaffolds: A (root) → B (subclass), gives both an `id` property
    via some HAS_PROPERTY-family relationship + property-type pair, and asserts
    the validator's verdict per the covariance matrix.
    """

    @staticmethod
    def _scaffold(nb, b_rel, b_type):
        """Create A.id (HAS_PROPERTY String) and B.id (b_rel b_type), with
        B SUBCLASS_OF A. Assumes b_type already exists in metaontology
        (e.g. 'String') or creates it as a subclass of String.
        """
        nb.run_query(
            f"""
            MATCH (node_root:OntologyNode {{label: 'Node'}})
            MATCH (str:OntologyNode {{label: 'String'}})
            MERGE (op_subtype:OntologyNode {{label: $b_type}})
                ON CREATE SET op_subtype.nid = randomUUID()
            MERGE (op_subtype)-[:SUBCLASS_OF]->(str)
            CREATE (a:OntologyNode {{label: 'A', nid: randomUUID()}})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {{label: 'B', nid: randomUUID()}})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {{label: 'id', nid: randomUUID()}})
            CREATE (a)-[:HAS_PROPERTY]->(a_id)
            CREATE (b_id:{b_type} {{label: 'id', nid: randomUUID()}})
            """,
            {"b_type": b_type},
        )
        nb.run_query(
            f"MATCH (b:OntologyNode {{label: 'B'}}) "
            f"MATCH (b_id:{b_type} {{label: 'id'}}) "
            f"CREATE (b)-[:{b_rel}]->(b_id)"
        )

    def test_covariant_override_silent(self, nb_meta):
        """B.id (HAS_KEY NarrowId) overrides A.id (HAS_PROPERTY String).
        NarrowId is a subclass of String → both dimensions narrow → OK, silent."""
        from neuro.base.metaontology import OntologyValidator
        self._scaffold(nb_meta, b_rel="HAS_KEY", b_type="NarrowId")
        nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert v.override_violations == []
        assert v.override_warnings == []
        validator = OntologyValidator(nb_meta)
        matches = [r for r in validator._find_property_overrides()
                   if r["class_label"] == "B" and r["prop_name"] == "id"]
        assert len(matches) == 1
        assert matches[0]["rel_relation"] == "narrower"
        assert matches[0]["type_relation"] == "narrower"
        assert validator._classify_override(matches[0]) == "ok"

    def test_pure_redeclaration_warns(self, nb_meta):
        """B.id (HAS_PROPERTY String) duplicates A.id (HAS_PROPERTY String).
        Same on both dimensions → warning."""
        self._scaffold(nb_meta, b_rel="HAS_PROPERTY", b_type="String")
        nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert v.override_violations == []
        assert len(v.override_warnings) == 1
        w = v.override_warnings[0]
        assert (w["class_label"], w["ancestor_label"], w["prop_name"]) == ("B", "A", "id")
        assert w["rel_relation"] == "same" and w["type_relation"] == "same"

    def test_relationship_widens_violates(self, nb_meta):
        """Cannot widen the relationship type — invert the lineage so A
        attaches via HAS_KEY and B widens to HAS_PROPERTY. → violation."""
        nb_meta.run_query(
            """
            MATCH (node_root:OntologyNode {label: 'Node'})
            MATCH (str:OntologyNode {label: 'String'})
            CREATE (a:OntologyNode {label: 'A', nid: randomUUID()})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {label: 'B', nid: randomUUID()})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {label: 'id', nid: randomUUID()})
            CREATE (a)-[:HAS_KEY]->(a_id)
            CREATE (b_id:String {label: 'id', nid: randomUUID()})
            CREATE (b)-[:HAS_PROPERTY]->(b_id)
            """
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert len(v.override_violations) == 1
        ov = v.override_violations[0]
        assert ov["rel_relation"] == "wider"

    def test_type_widens_violates(self, nb_meta):
        """B.id (HAS_PROPERTY GenericProp) where GenericProp is a parent of
        String. → type widens → violation."""
        nb_meta.run_query(
            """
            MATCH (node_root:OntologyNode {label: 'Node'})
            MATCH (str:OntologyNode {label: 'String'})
            MATCH (op_root:OntologyNode {label: 'OntologyProperty'})
            CREATE (gp:OntologyNode {label: 'GenericProp', nid: randomUUID()})
                -[:SUBCLASS_OF]->(op_root)
            CREATE (str)-[:SUBCLASS_OF]->(gp)
            CREATE (a:OntologyNode {label: 'A', nid: randomUUID()})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {label: 'B', nid: randomUUID()})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {label: 'id', nid: randomUUID()})
            CREATE (a)-[:HAS_PROPERTY]->(a_id)
            CREATE (b_id:GenericProp {label: 'id', nid: randomUUID()})
            CREATE (b)-[:HAS_PROPERTY]->(b_id)
            """
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert len(v.override_violations) == 1
        ov = v.override_violations[0]
        assert ov["type_relation"] == "wider"

    def test_unrelated_type_violates(self, nb_meta):
        """B.id is typed SiblingType — a fresh subclass of OntologyProperty
        sitting parallel to the String lineage. → unrelated → violation."""
        nb_meta.run_query(
            """
            MATCH (node_root:OntologyNode {label: 'Node'})
            MATCH (op_root:OntologyNode {label: 'OntologyProperty'})
            CREATE (sibling:OntologyNode {label: 'SiblingType', nid: randomUUID()})
                -[:SUBCLASS_OF]->(op_root)
            CREATE (a:OntologyNode {label: 'A', nid: randomUUID()})
                -[:SUBCLASS_OF]->(node_root)
            CREATE (b:OntologyNode {label: 'B', nid: randomUUID()})
                -[:SUBCLASS_OF]->(a)
            CREATE (a_id:String {label: 'id', nid: randomUUID()})
            CREATE (a)-[:HAS_PROPERTY]->(a_id)
            CREATE (b_id:SiblingType {label: 'id', nid: randomUUID()})
            CREATE (b)-[:HAS_PROPERTY]->(b_id)
            """
        )
        assert not nb_meta.metaontology.is_ontology_valid()
        v = nb_meta.metaontology.violations
        assert len(v.override_violations) == 1
        ov = v.override_violations[0]
        assert ov["type_relation"] == "unrelated"


class TestImportReconciliation:
    """`import_nfx` must not destroy what the file being imported does not own.

    The old clear — `MATCH (m:OntologyMetadata {nid})-[:DEFINES]->(n) DETACH
    DELETE n` — is scoped by who defines a node in the graph's *last* state,
    not by what the file on disk declares, and `DETACH` takes every edge on
    those nodes with them. A hoist across files is exactly the operation that
    makes those two disagree (PLAN-2026-143, issue #25).
    """

    CORE = "aed7bdc4-bde9-4bff-b083-aa74ec4166fb"
    DEPENDENT = "5f40d75f-1a92-4fd1-9d15-64c176146e64"
    KNOWLEDGE = "6c223d58-5249-4849-adc7-65da90aca557"
    SHARED = "5e7160af-c5bd-451d-b9ba-2a06a31811f8"
    LOCAL = "446d7dbd-e637-4f40-a3d0-3f2a8967a30d"
    METRIC = "d7076410-3ff0-4022-9fbc-d93c4af4df34"
    DROPPED = "500dc293-d43d-4f10-8170-ae9663c80b2c"

    @staticmethod
    def _write(tmp_path, name, nid, version, nodes, relationships=(), dependencies=()):
        from neuro.base import nfx
        path = tmp_path / f"{name}-{version}.nfx"
        nfx.write(path, nfx.Nfx(
            nid=nid, type="ontology", name=name, version=version,
            dependencies=tuple(dependencies), nodes=tuple(nodes),
            relationships=tuple(relationships),
        ))
        return path

    @classmethod
    def _node(cls, nid, label):
        return {"nid": nid, "labels": ["OntologyNode"], "properties": {"label": label}}

    def _exists(self, nb, nid):
        return bool(nb.get_data("MATCH (n {nid: $nid}) RETURN n.nid", {"nid": nid}))

    def _edge(self, nb, from_nid, to_nid, rel_type):
        rows = nb.get_data(
            f"MATCH (a {{nid: $f}})-[:{rel_type}]->(b {{nid: $t}}) RETURN count(*) AS c",
            {"f": from_nid, "t": to_nid},
        )
        return rows[0]["c"] > 0

    def test_hoist_keeps_node(self, nb_meta, tmp_path):
        """Moving a node into a dependency must not lose it (issue #25)."""
        # Release 1: the dependent owns both nodes.
        old = self._write(
            tmp_path, "dependent", self.DEPENDENT, "1.0",
            [self._node(self.SHARED, "Shared"), self._node(self.LOCAL, "Local")],
        )
        nb_meta.metaontology.import_nfx(old)
        assert self._exists(nb_meta, self.SHARED)

        # Release 2: Shared is hoisted into the core; the dependent declares
        # only Local and points at Shared through the dependency.
        core = self._write(
            tmp_path, "core", self.CORE, "1.0", [self._node(self.SHARED, "Shared")],
        )
        new = self._write(
            tmp_path, "dependent", self.DEPENDENT, "1.1",
            [self._node(self.LOCAL, "Local")],
            [{"from": self.LOCAL, "to": self.SHARED, "type": "SUBCLASS_OF"}],
            [(self.CORE, "1.0")],
        )
        nb_meta.metaontology.import_nfx(core)
        nb_meta.metaontology.import_nfx(new)

        assert self._exists(nb_meta, self.SHARED), "hoisted node deleted by its old owner"
        assert self._edge(nb_meta, self.LOCAL, self.SHARED, "SUBCLASS_OF")

    def test_reimport_keeps_dependent_edges(self, nb_meta, tmp_path):
        """Re-importing a core must not take dependents' edges into it."""
        core = self._write(
            tmp_path, "core", self.CORE, "1.0", [self._node(self.SHARED, "Shared")],
        )
        dependent = self._write(
            tmp_path, "dependent", self.DEPENDENT, "1.0",
            [self._node(self.LOCAL, "Local")],
            [{"from": self.LOCAL, "to": self.SHARED, "type": "SUBCLASS_OF"}],
            [(self.CORE, "1.0")],
        )
        nb_meta.metaontology.import_nfx(core)
        nb_meta.metaontology.import_nfx(dependent)
        assert self._edge(nb_meta, self.LOCAL, self.SHARED, "SUBCLASS_OF")

        bumped = self._write(
            tmp_path, "core", self.CORE, "1.1", [self._node(self.SHARED, "Shared")],
        )
        nb_meta.metaontology.import_nfx(bumped)

        assert self._edge(nb_meta, self.LOCAL, self.SHARED, "SUBCLASS_OF"), \
            "dependent's SUBCLASS_OF severed by the core's re-import"

    def test_reimport_keeps_instance_edges(self, nb_meta, tmp_path):
        """Edges from outside the ontology layer must survive a re-import.

        Mode 3 of PLAN-2026-143: measured components and metric definitions
        point straight at `OntologyNode`s, and no ontology re-import restores
        those edges once `DETACH` has taken them.
        """
        core = self._write(
            tmp_path, "core", self.CORE, "1.0", [self._node(self.SHARED, "Shared")],
        )
        nb_meta.metaontology.import_nfx(core)
        nb_meta.run_query(
            """
            MATCH (c {nid: $shared})
            CREATE (k:KnowledgeMetadata {nid: $knowledge, name: 'pages'})
            CREATE (m:MetricDefinition {nid: $metric, label: 'Coverage'})
            CREATE (k)-[:DEFINES]->(m)
            CREATE (m)-[:APPLIES_TO]->(c)
            """,
            {"shared": self.SHARED, "knowledge": self.KNOWLEDGE, "metric": self.METRIC},
        )

        bumped = self._write(
            tmp_path, "core", self.CORE, "1.1", [self._node(self.SHARED, "Shared")],
        )
        nb_meta.metaontology.import_nfx(bumped)

        assert self._edge(nb_meta, self.METRIC, self.SHARED, "APPLIES_TO"), \
            "APPLIES_TO from a knowledge-defined node severed by the re-import"

    def test_undeclared_node_is_orphaned_not_deleted(self, nb_meta, tmp_path):
        """A node dropped from a file is kept and un-DEFINES'd, never deleted."""
        first = self._write(
            tmp_path, "core", self.CORE, "1.0",
            [self._node(self.SHARED, "Shared"), self._node(self.DROPPED, "Dropped")],
        )
        nb_meta.metaontology.import_nfx(first)

        second = self._write(
            tmp_path, "core", self.CORE, "1.1", [self._node(self.SHARED, "Shared")],
        )
        nb_meta.metaontology.import_nfx(second)

        assert self._exists(nb_meta, self.DROPPED), "undeclared node must be kept"
        assert not self._edge(nb_meta, self.CORE, self.DROPPED, "DEFINES"), \
            "the dropping ontology must release its DEFINES"
