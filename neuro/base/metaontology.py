from neuro.base import nfx
from neuro.base.schema import Metaproperties, ONTOLOGY_OBJECTS, Violations
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
        for kind in ONTOLOGY_OBJECTS:
            self.instances[kind] = self._fetch_instances(kind)

    def _is_connected(self):
        """Check if the ontology graph is a single connected component."""
        query = f"""
        MATCH (root:OntologyNode)
        WHERE root.label IN {list(ONTOLOGY_OBJECTS)}
        MATCH (root)<-[:SUBCLASS_OF*0..]-(type)
        MATCH (n)
        WHERE type.label IN labels(n)
        WITH collect(DISTINCT n) AS ontology_nodes
        WITH ontology_nodes, ontology_nodes[0] AS start
        CALL apoc.path.subgraphNodes(start, {{}}) YIELD node
        WITH count(node) AS reachable, size(ontology_nodes) AS total
        RETURN reachable = total AS connected
        """
        data = self._nb.get_data(query)
        return data[0]["connected"]

    def validate(self):
        """Run all validation checks. Returns an OntologyViolations instance."""
        ontology_violations = OntologyViolations()

        for kind in ONTOLOGY_OBJECTS:
            for instance in self.instances[kind]:
                label = instance["label"]
                ontology_object_type = instance["ontology_object_type"]
                props = instance["properties"]

                metaproperties = Metaproperties.from_ontology(self._nb, ontology_object_type)
                v = metaproperties.validate_properties(props)

                if v:
                    ontology_violations.violations.append((label, ontology_object_type, v))

        ontology_violations.disconnected = not self._is_connected()

        return ontology_violations


class OntologyViolations:
    """Ontology-level violations: collects per-instance Violations and structural issues."""

    def __init__(self):
        self.violations: list[tuple[str, str, Violations]] = []
        self.disconnected: bool = False
        self.redundant_labels: list[str] = []
        self.redundant_relationships: list[str] = []
        self.redundant_properties: list[str] = []

    def __bool__(self):
        return any([
            self.violations, self.disconnected, self.redundant_labels,
            self.redundant_relationships, self.redundant_properties,
        ])

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

        if not lines:
            return f"{SUCCESS} Ontology valid"
        return "\n".join(lines)


class Metaontology:
    """Export/import the metaontology (node types, relationship types) as NFX."""

    def __init__(self, nb):
        self._nb = nb

    def import_nfx(self, path):
        """Import metaontology from an NFX file. Merges nodes and relationships
        without ontology validation (schema defines the validation rules)."""
        data = nfx.read(path)

        nid = data.get("nid")
        name = data.get("name")
        if nid and name:
            properties = {k: data[k] for k in ("name", "version", "description") if k in data}
            self._nb.run_query(
                """
                MERGE (m:OntologyMetadata {`neuro.id`: $neuro_id})
                SET m += $props
                """,
                {"neuro_id": nid, "props": properties},
            )
            for dep in data.get("dependencies", []):
                dep_nid = dep.split("@")[0]
                self._nb.run_query(
                    """
                    MATCH (m:OntologyMetadata {`neuro.id`: $neuro_id})
                    MATCH (d:OntologyMetadata {`neuro.id`: $dep_nid})
                    MERGE (m)-[:DEPENDS_ON]->(d)
                    """,
                    {"neuro_id": nid, "dep_nid": dep_nid},
                )

        for entry in data.get("nodes", []):
            labels_str = ":".join(entry["labels"])
            query = f"""
            MERGE (n:{labels_str} {{`neuro.id`: $neuro_id}})
            SET n += $properties
            """
            self._nb.run_query(query, {
                "neuro_id": entry["nid"],
                "properties": entry.get("properties", {}),
            })

        for rel in data.get("relationships", []):
            query = f"""
            MATCH (a {{`neuro.id`: $from_id}})
            MATCH (b {{`neuro.id`: $to_id}})
            MERGE (a)-[r:{rel["type"]}]->(b)
            SET r += $properties
            """
            self._nb.run_query(query, {
                "from_id": rel["from"],
                "to_id": rel["to"],
                "properties": rel.get("properties", {}),
            })

    def is_ontology_valid(self):
        """Validate metaontology structure. Returns True if valid, False otherwise."""
        count = self._nb.count("Metaontology")
        if not count:
            raise exceptions.NoOntology

        validator = OntologyValidator(self._nb)
        self.violations = validator.validate()
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

        return nfx.write(
            path, result["nodes"], result["relationships"],
            nid=meta.get("nid", ""),
            name=meta.get("name", "Metaontology"),
            version=meta.get("version", ""),
            description=meta.get("description", ""),
        )
