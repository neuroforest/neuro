from neuro.base import nfx
from neuro.base.schema import ObjectValidator, OntologyViolations
from neuro.utils import exceptions, terminal_style

ONTOLOGY_OBJECTS = ("OntologyNode", "OntologyRelationship", "OntologyProperty")


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
            print(f"\n[FETCH] {kind}: {len(self.instances[kind])} instances")
            for inst in self.instances[kind]:
                print(f"  - {inst['label']} (type={inst['type']}, labels={inst['labels']})")

    def validate(self):
        """Run all validation checks. Returns an OntologyViolations instance."""
        violations = OntologyViolations()
        validator = ObjectValidator(self._nb, None)
        B, G, R, Y, RST = terminal_style.BOLD, terminal_style.GREEN, terminal_style.RED, terminal_style.YELLOW, terminal_style.RESET

        for kind in ONTOLOGY_OBJECTS:
            print(f"\n{B}{Y}{kind}{RST}")
            print(f"{Y}{'─'*40}{RST}")

            for instance in self.instances[kind]:
                label = instance["label"]
                itype = instance["type"]
                props = instance["properties"]

                metaproperties = validator.get_metaproperties(itype)
                v = metaproperties.validate_properties(props)

                if v.missing_properties or v.undefined_properties:
                    status = f"{R}✘{RST}"
                else:
                    status = f"{G}✔{RST}"

                print(f"{status} {B}{label}{RST} {Y}({itype}){RST}")
                print(f"  properties: {list(props.keys())}")
                print(f"  expected: {list(metaproperties.keys())}")
                if v.missing_properties:
                    print(f"  {R}missing: {[p for p, _ in v.missing_properties]}{RST}")
                    violations.missing_properties.extend(
                        [(label, p) for p, _ in v.missing_properties]
                    )
                if v.undefined_properties:
                    print(f"  {R}undefined: {v.undefined_properties}{RST}")
                    violations.redundant_properties.extend(
                        [f"{label}.{p}" for p in v.undefined_properties]
                    )

                input("Next?")

        print(f"\n{B}{'─'*40}{RST}")
        if violations:
            print(f"{R}{B}VIOLATIONS:{RST} {repr(violations)}")
        else:
            print(f"{G}{B}ALL VALID{RST}")
        return violations


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
        if not self.is_ontology_valid():
            raise ValueError("Metaontology validation failed:\n" + repr(self.violations))

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
