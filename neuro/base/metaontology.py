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
        RETURN n.label as label, type.label as type, labels(n) as labels, properties(n) as properties
        """
        data = self._nb.get_data(query, {"kind": kind})
        return [dict(record) for record in data]

    def _fetch_data(self):
        for kind in ONTOLOGY_OBJECTS:
            self.instances[kind] = self._fetch_instances(kind)

    def validate(self):
        """Run all validation checks. Returns an OntologyViolations instance."""
        ontology_violations = OntologyViolations()

        for kind in ONTOLOGY_OBJECTS:
            for instance in self.instances[kind]:
                label = instance["label"]
                itype = instance["type"]
                props = instance["properties"]

                metaproperties = Metaproperties.from_ontology(self._nb, itype)
                v = metaproperties.validate_properties(props)

                if v:
                    ontology_violations.violations.append((label, itype, v))

        return ontology_violations


class OntologyViolations:
    """Ontology-level violations: collects per-instance Violations and structural issues."""

    def __init__(self):
        self.violations: list[tuple[str, str, Violations]] = []
        self.orphan_nodes: list[str] = []
        self.redundant_labels: list[str] = []
        self.redundant_relationships: list[str] = []
        self.redundant_properties: list[str] = []

    def __bool__(self):
        return any([
            self.violations, self.orphan_nodes, self.redundant_labels,
            self.redundant_relationships, self.redundant_properties,
        ])

    def __repr__(self):
        B, G, R, Y, RST = terminal_style.BOLD, terminal_style.GREEN, terminal_style.RED, terminal_style.YELLOW, terminal_style.RESET
        lines = []

        for label, itype, v in self.violations:
            lines.append(f"{R}✘{RST} {B}{label}{RST} {Y}({itype}){RST}")
            lines.append(repr(v))

        if self.orphan_nodes:
            lines.append(f"Orphan nodes: {self.orphan_nodes}")
        if self.redundant_labels:
            lines.append(f"Redundant labels: {self.redundant_labels}")
        if self.redundant_relationships:
            lines.append(f"Redundant relationships: {self.redundant_relationships}")
        if self.redundant_properties:
            lines.append(f"Redundant properties: {self.redundant_properties}")

        if not lines:
            return f"{G}{B}ALL VALID{RST}"
        return "\n".join(lines)


class Metaontology:
    """Export/import the metaontology (node types, relationship types) as NFX."""

    def __init__(self, nb):
        self._nb = nb

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

        return nfx.write(
            path, result["nodes"], result["relationships"],
            name="Metaontology"
        )
