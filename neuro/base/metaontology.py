import json
import os

from neuro.base import nfx, schema
from neuro.utils import exceptions, terminal_style


class OntologyValidator:
    """Validate ontology structure against the metaontology definition."""

    def __init__(self, nb):
        self._nb = nb
        self.instances = {}
        self._fetch_data()

    def _fetch_instances(self, kind):
        """Fetch all instances of an ontology kind via SUBCLASS_OF hierarchy."""
        query = """
        MATCH (root:OntologyNode {label: $kind})
        MATCH (type)-[:SUBCLASS_OF*0..]->(root)
        MATCH (n)
        WHERE type.label IN labels(n)
        RETURN n.label as label, type.label as ontology_object_type, labels(n) as labels,
               properties(n) as properties
        """
        data = self._nb.get_data(query, {"kind": kind})
        return [dict(record) for record in data]

    def _fetch_data(self):
        for kind in json.loads(os.environ["ONTOLOGY_OBJECTS"]):
            self.instances[kind] = self._fetch_instances(kind)

    def _is_connected(self):
        """Check if the ontology graph is a single connected component."""
        structural = json.loads(os.environ["ONTOLOGY_OBJECTS"])
        query = f"""
        MATCH (root:OntologyNode)
        WHERE root.label IN {structural}
        MATCH (root)<-[:SUBCLASS_OF*0..]-(type)
        MATCH (n)
        WHERE type.label IN labels(n) AND NOT n:OntologyMetadata
        WITH collect(DISTINCT n) AS ontology_nodes
        WITH ontology_nodes, ontology_nodes[0] AS start
        CALL apoc.path.subgraphNodes(start, {{whitelistNodes: ontology_nodes}}) YIELD node
        WITH count(node) AS reachable, size(ontology_nodes) AS total
        RETURN reachable = total AS connected
        """
        data = self._nb.get_data(query)
        return data[0]["connected"]

    def validate(self, strict=False):
        """Run all validation checks. Returns an OntologyViolations instance."""
        ontology_violations = OntologyViolations()

        for kind in json.loads(os.environ["ONTOLOGY_OBJECTS"]):
            for instance in self.instances[kind]:
                label = instance["label"]
                ontology_object_type = instance["ontology_object_type"]
                props = instance["properties"]

                metaproperties = schema.Metaproperties.from_ontology(self._nb, ontology_object_type)
                v = metaproperties.validate_properties(props)

                if v:
                    ontology_violations.violations.append((label, ontology_object_type, v))

        if "OntologyProperty" in self.instances:
            specific = {i["label"] for i in self.instances["OntologyProperty"]
                        if i["ontology_object_type"] != "OntologyProperty"}
            ontology_violations.generic_properties = sorted(
                {i["label"] for i in self.instances["OntologyProperty"]
                 if i["ontology_object_type"] == "OntologyProperty"}
                - specific
            )

            if strict:
                missing = {}
                for i in self.instances["OntologyProperty"]:
                    pt = i["ontology_object_type"]
                    if pt == "OntologyProperty" or pt in missing or schema.has_validator(pt):
                        continue
                    missing[pt] = i["label"]
                ontology_violations.unvalidated_property_types = sorted(missing.items())

        ontology_violations.disconnected = not self._is_connected()

        return ontology_violations


class OntologyViolations:
    """Ontology-level violations: collects per-instance Violations and structural issues."""

    def __init__(self):
        self.violations: list[tuple[str, str, schema.Violations]] = []
        self.disconnected: bool = False
        self.redundant_labels: list[str] = []
        self.redundant_relationships: list[str] = []
        self.redundant_properties: list[str] = []
        self.generic_properties: list[str] = []
        self.unvalidated_property_types: list[tuple[str, str]] = []

    def __bool__(self):
        return any([
            self.violations, self.disconnected, self.redundant_labels,
            self.redundant_relationships, self.redundant_properties,
            self.unvalidated_property_types,
        ])

    def __iter__(self):
        for label, otype, v in self.violations:
            yield f"{label} ({otype}): {v}"
        if self.disconnected:
            yield "disconnected"
        for rl in self.redundant_labels:
            yield f"redundant label: {rl}"
        for rr in self.redundant_relationships:
            yield f"redundant relationship: {rr}"
        for rp in self.redundant_properties:
            yield f"redundant property: {rp}"
        for ptype, example in self.unvalidated_property_types:
            yield f"unvalidated property type: {ptype} (e.g. {example})"

    @property
    def warnings(self):
        B, Y, RST = terminal_style.BOLD, terminal_style.YELLOW, terminal_style.RESET
        for prop in self.generic_properties:
            yield f"{Y}warning: {B}{prop}{RST}{Y} uses generic OntologyProperty{RST}"

    def __repr__(self):
        B, SUCCESS, FAIL, Y, RST = (
            terminal_style.BOLD, terminal_style.SUCCESS, terminal_style.FAIL,
            terminal_style.YELLOW, terminal_style.RESET
        )
        lines = []

        for label, ontology_object_type, v in self.violations:
            lines.append(f"{FAIL} {B}{label}{RST} {Y}({ontology_object_type}){RST}")
            lines.append(repr(v))

        if self.disconnected:
            lines.append("Disconnected: ontology graph is not fully connected")
        if self.redundant_labels:
            lines.append(f"Redundant labels: {self.redundant_labels}")
        if self.redundant_relationships:
            lines.append(f"Redundant relationships: {self.redundant_relationships}")
        if self.redundant_properties:
            lines.append(f"Redundant properties: {self.redundant_properties}")
        for ptype, example in self.unvalidated_property_types:
            lines.append(f"{FAIL} unvalidated property type: {B}{ptype}{RST} (e.g. {example})")

        for w in self.warnings:
            lines.append(f"  {w}")

        if not lines:
            return f"{SUCCESS} Ontology valid"
        return "\n".join(lines)


class Metaontology:
    """Export/import the metaontology (node types, relationship types) as NFX."""

    def __init__(self, nb):
        self._nb = nb

    @staticmethod
    def _version_tuple(version_str):
        """Parse a version string like '2.1' into a comparable tuple (2, 1)."""
        return tuple(int(x) for x in version_str.split("."))

    def _import_dependencies(self, dependencies, index=None, on_import=None, _depth=1):
        """Ensure dependencies are in the DB. Import from index if missing or below minimum.

        Version pins are treated as minimum versions (Go-style): @2.1 means >=2.1.
        The resolver keeps the highest version already loaded if it satisfies the minimum.

        `dependencies` is an iterable of `(nid, version)` pairs (as on `Nfx.dependencies`).

        on_import(name, imported, depth): callback for each dependency.
            imported=True if freshly imported, False if already loaded.
            depth is the dependency depth (1 for direct, 2+ for transitive).
        """
        for dep_nid, dep_version in dependencies:
            data = self._nb.get_data(
                """
                MATCH (m:OntologyMetadata {`neuro.id`: $nid})
                RETURN m.name as name, m.version as version
                """,
                {"nid": dep_nid},
            )
            if data and (not dep_version or
                         self._version_tuple(data[0]["version"]) >= self._version_tuple(dep_version)):
                if on_import:
                    on_import(data[0]["name"], imported=False, depth=_depth)
                if index:
                    dep_path = index.resolve(dep_nid)
                    if dep_path:
                        sub_deps = nfx.read(dep_path).dependencies
                        self._import_dependencies(sub_deps, index, on_import, _depth=_depth + 1)
                continue
            if not index:
                raise exceptions.NfxViolation(f"Missing dependency: {dep_nid}@{dep_version}")
            dep_path = index.resolve(dep_nid)
            if not dep_path:
                raise exceptions.NfxViolation(f"Dependency {dep_nid}@{dep_version} not found in index")
            self.import_nfx(dep_path, index=index, on_import=on_import, _depth=_depth)
            dep_name = nfx.read(dep_path).name or dep_path.stem
            if on_import:
                on_import(dep_name, imported=True, depth=_depth)

    def _resolver(self, index=None):
        """Return a dep-resolver for `nfx.NfxTree`: index file, fallback to DB.

        Returns an `Nfx` (or None). The DB-fallback Nfx carries empty version
        strings on dependencies — only `node_nids`/`dep_nids` are consulted by
        the walk, so the placeholder is fine.
        """
        def resolve(dep_nid):
            if index:
                dep_path = index.resolve(dep_nid)
                if dep_path:
                    return nfx.read(dep_path)
            rows = self._nb.get_data(
                """
                MATCH (m:OntologyMetadata {`neuro.id`: $nid})
                OPTIONAL MATCH (m)-[:DEFINES]->(n)
                OPTIONAL MATCH (m)-[:DEPENDS_ON]->(d:OntologyMetadata)
                RETURN collect(DISTINCT n.`neuro.id`) as nids,
                       collect(DISTINCT d.`neuro.id`) as dep_nids
                """,
                {"nid": dep_nid},
            )
            if not rows:
                return None
            return nfx.Nfx(
                nodes=tuple({"nid": x} for x in rows[0]["nids"] if x),
                dependencies=tuple((x, "") for x in rows[0]["dep_nids"] if x),
            )
        return resolve

    def import_nfx(self, path, index=None, on_import=None, _depth=0):
        """Import an ontology from an NFX file.

        Clears and rewrites this ontology's nodes. Dependencies are checked
        in the DB; if missing or version mismatch, imported via the index.

        on_import(name, imported, depth): optional callback for dependency status.
        """
        doc = nfx.read(path)

        # Ensure dependencies are present in the DB.
        self._import_dependencies(doc.dependencies, index, on_import, _depth=_depth + 1)

        # Validate referential integrity.
        try:
            tree = nfx.NfxTree(doc, self._resolver(index))
        except exceptions.NfxCycle as e:
            raise exceptions.NfxViolation(
                f"Dependency cycle for {path}: {' -> '.join(e.args[0])}"
            )
        violations = nfx.validate(doc, tree.all_node_nids(scope="dependencies"))
        if violations["unresolved"] or violations["foreign"]:
            msgs = []
            for rel in violations["unresolved"]:
                msgs.append(f"  unresolved: {rel['from']} -> {rel['to']} ({rel['type']})")
            for rel in violations["foreign"]:
                msgs.append(f"  foreign: {rel['from']} -> {rel['to']} ({rel['type']})")
            raise exceptions.NfxViolation(
                f"NFX validation failed for {path}:\n" + "\n".join(msgs)
            )

        # Clear and rewrite this ontology's nodes.
        if doc.nid and doc.name:
            self._nb.run_query(
                """
                MATCH (m:OntologyMetadata {`neuro.id`: $nid})-[:DEFINES]->(n)
                DETACH DELETE n
                """,
                {"nid": doc.nid},
            )
            properties = {k: v for k, v in (
                ("name", doc.name), ("version", doc.version), ("description", doc.description),
            ) if v}
            self._nb.run_query(
                "MERGE (m:OntologyMetadata {`neuro.id`: $nid}) SET m += $props",
                {"nid": doc.nid, "props": properties},
            )
            for dep_nid, _ in doc.dependencies:
                self._nb.run_query(
                    """
                    MATCH (m:OntologyMetadata {`neuro.id`: $nid})
                    MATCH (d:OntologyMetadata {`neuro.id`: $dep_nid})
                    MERGE (m)-[:DEPENDS_ON]->(d)
                    """,
                    {"nid": doc.nid, "dep_nid": dep_nid},
                )

        for entry in doc.nodes:
            labels_str = ":".join(entry["labels"])
            self._nb.run_query(
                f"MERGE (n:{labels_str} {{`neuro.id`: $nid}}) SET n += $props",
                {"nid": entry["nid"], "props": entry.get("properties", {})},
            )
            if doc.nid:
                self._nb.run_query(
                    f"""
                    MATCH (m:OntologyMetadata {{`neuro.id`: $ontology_nid}})
                    MATCH (n:{labels_str} {{`neuro.id`: $node_nid}})
                    MERGE (m)-[:DEFINES]->(n)
                    """,
                    {"ontology_nid": doc.nid, "node_nid": entry["nid"]},
                )

        for rel in doc.relationships:
            self._nb.run_query(
                f"""
                MATCH (:OntologyMetadata)-[:DEFINES]->(a {{`neuro.id`: $from_id}})
                MATCH (:OntologyMetadata)-[:DEFINES]->(b {{`neuro.id`: $to_id}})
                MERGE (a)-[r:{rel["type"]}]->(b)
                SET r += $props
                """,
                {"from_id": rel["from"], "to_id": rel["to"],
                 "props": rel.get("properties", {})},
            )

    def is_ontology_valid(self, strict=False):
        """Validate metaontology structure. Returns True if valid, False otherwise."""
        count = self._nb.count("Metaontology")
        if not count:
            raise exceptions.NoOntology

        validator = OntologyValidator(self._nb)
        self.violations = validator.validate(strict=strict)
        return not bool(self.violations)

    def export_nfx(self, path=None):
        """Export metaontology nodes and their relationships to an NFX file."""
        query = """
        MATCH (:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (:OntologyNode:Metaontology)-[:REQUIRE_PROPERTY]->(prop:Metaontology)
        WITH collect(DISTINCT prop.label) as required_keys

        MATCH (n:Metaontology)-[r]-(m:Metaontology)
        WHERE n.`neuro.id` IS NOT NULL AND m.`neuro.id` IS NOT NULL
        WITH required_keys,
             collect(DISTINCT {nid: n.`neuro.id`, labels: labels(n),
                 properties: apoc.map.fromPairs(
                     [k IN required_keys WHERE properties(n)[k] IS NOT NULL
                      | [k, properties(n)[k]]])})
             + collect(DISTINCT {nid: m.`neuro.id`, labels: labels(m),
                 properties: apoc.map.fromPairs(
                     [k IN required_keys WHERE properties(m)[k] IS NOT NULL
                      | [k, properties(m)[k]]])}) as allNodes,
             collect({from: startNode(r).`neuro.id`, to: endNode(r).`neuro.id`,
                 type: type(r), properties: properties(r)}) as relationships
        UNWIND allNodes as n
        WITH collect(DISTINCT n) as nodes, relationships
        RETURN nodes, relationships
        """
        result = self._nb.get_data(query)[0]

        meta_query = """
        MATCH (m:OntologyMetadata {name: "Metaontology"})
        RETURN m.`neuro.id` as nid, m.name as name, m.version as version,
               m.description as description
        """
        meta = self._nb.get_data(meta_query)
        meta = meta[0] if meta else {}

        doc = nfx.Nfx.from_dict({
            "nid": meta.get("nid", ""),
            "name": meta.get("name", "Metaontology"),
            "description": meta.get("description", ""),
            "version": meta.get("version", ""),
            "nodes": result["nodes"],
            "relationships": result["relationships"],
        })
        nfx.write(path, doc)
        return doc
