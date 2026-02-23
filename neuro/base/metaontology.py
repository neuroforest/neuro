from pathlib import Path

from neuro.base import nfx
from neuro.core import Node


class Metaontology:
    """Export/import the metaontology (node types, relationship types) as NFX."""

    def __init__(self, nb):
        self._nb = nb

    def is_valid(self):
        """Validate metaontology structure. Returns True if valid, False otherwise."""
        self.violations = []

        count = self._nb.count("Metaontology")
        if not count:
            self.violations.append("No Metaontology nodes found")
            return False

        # Metaontology should be a connected graph
        orphans = self._nb.get_data("""
        MATCH (n:Metaontology)
        WHERE NOT (n)-[]-(:Metaontology)
        RETURN n.label as label
        """)
        for node in orphans:
            self.violations.append(f"Orphan node: {node['label']}")

        # Every label, property key and relationship should be explicitly defined
        undefined_labels = self._nb.get_data("""
        MATCH (sub:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (:OntologyNode:Metaontology {label: "OntologyNode"})
        WITH collect(DISTINCT sub.label) as node_types
        MATCH (n:Metaontology)
        UNWIND labels(n) as label
        WITH collect(DISTINCT label) as used_labels, node_types
        UNWIND used_labels as label
        OPTIONAL MATCH (on:Metaontology {label: label})
        WHERE any(l IN labels(on) WHERE l IN node_types)
        WITH label WHERE on IS NULL
        RETURN label
        """)
        for node in undefined_labels:
            self.violations.append(f"Undefined label: {node['label']}")

        undefined_rels = self._nb.get_data("""
        MATCH (sub:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (:OntologyNode:Metaontology {label: "OntologyRelationship"})
        WITH collect(DISTINCT sub.label) as rel_types
        MATCH (:Metaontology)-[r]-(:Metaontology)
        WITH collect(DISTINCT type(r)) as used_types, rel_types
        UNWIND used_types as rel_type
        OPTIONAL MATCH (or:Metaontology {label: rel_type})
        WHERE any(l IN labels(or) WHERE l IN rel_types)
        WITH rel_type WHERE or IS NULL
        RETURN rel_type
        """)
        for rel in undefined_rels:
            self.violations.append(f"Undefined relationship: {rel['rel_type']}")

        missing_props = self._nb.get_data("""
        MATCH (on:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (parent:OntologyNode:Metaontology)-[:REQUIRE_PROPERTY]->(prop:Metaontology)
        WITH on.label as node_type, collect(DISTINCT prop.label) as required_keys
        MATCH (n:Metaontology)
        WHERE node_type IN labels(n)
        WITH n, node_type, required_keys, keys(n) as node_keys
        UNWIND required_keys as req
        WITH n.label as node_label, node_type, req
        WHERE NOT req IN keys(n)
        RETURN node_label, node_type, req as missing_key
        """)
        for prop in missing_props:
            self.violations.append(
                f"Missing property: {prop['node_label']} ({prop['node_type']}) missing {prop['missing_key']}"
            )

        # Every definition should be in use
        redundant_labels = self._nb.get_data("""
        MATCH (sub:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (:OntologyNode:Metaontology {label: "OntologyNode"})
        WITH collect(DISTINCT sub.label) as node_types
        MATCH (sub:Metaontology)-[:SUBCLASS_OF*0..]->
              (:Metaontology {label: "HAS_PROPERTY"})
        WITH node_types, collect(DISTINCT sub.label) as prop_rel_types
        MATCH (sub:Metaontology)-[:SUBCLASS_OF*0..]->
              (:Metaontology {label: "HAS_RELATIONSHIP"})
        WITH node_types, prop_rel_types, collect(DISTINCT sub.label) as has_rel_types
        WITH node_types, prop_rel_types + has_rel_types as non_redundant_rel_types
        MATCH (def:Metaontology)
        WHERE any(l IN labels(def) WHERE l IN node_types)
        AND NOT any(l IN [(def)-[r]->(:Metaontology) | type(r)] WHERE l IN non_redundant_rel_types)
        AND NOT (:Metaontology)-[]->(def)
        WITH def.label as defined_label
        MATCH (n:Metaontology)
        UNWIND labels(n) as used_label
        WITH collect(DISTINCT used_label) as used_labels, defined_label
        WHERE NOT defined_label IN used_labels
        RETURN defined_label
        """)
        for node in redundant_labels:
            self.violations.append(f"Redundant label: {node['defined_label']}")

        redundant_rels = self._nb.get_data("""
        MATCH (sub:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (:OntologyNode:Metaontology {label: "OntologyRelationship"})
        WITH collect(DISTINCT sub.label) as rel_types
        MATCH (def:Metaontology)
        WHERE any(l IN labels(def) WHERE l IN rel_types)
        AND NOT (:Metaontology)-[]->(def)
        WITH def.label as defined_rel
        MATCH (:Metaontology)-[r]-(:Metaontology)
        WITH collect(DISTINCT type(r)) as used_rels, defined_rel
        WHERE NOT defined_rel IN used_rels
        RETURN defined_rel
        """)
        for rel in redundant_rels:
            self.violations.append(f"Redundant relationship: {rel['defined_rel']}")

        redundant_props = self._nb.get_data("""
        MATCH (sub:OntologyNode:Metaontology)-[:SUBCLASS_OF*0..]->
              (:OntologyNode:Metaontology {label: "OntologyProperty"})
        WITH collect(DISTINCT sub.label) as prop_types
        MATCH (def:Metaontology)
        WHERE any(l IN labels(def) WHERE l IN prop_types)
        AND NOT (:Metaontology)-[]->(def)
        WITH def.label as defined_prop
        MATCH (n:Metaontology)
        UNWIND keys(n) as used_key
        WITH collect(DISTINCT used_key) as used_keys, defined_prop
        WHERE NOT defined_prop IN used_keys
        RETURN defined_prop
        """)
        for prop in redundant_props:
            self.violations.append(f"Redundant property: {prop['defined_prop']}")

        return not self.violations

    def export_nfx(self, path=None):
        """Export metaontology nodes and their relationships to an NFX file."""
        if not self.is_valid():
            raise ValueError("Metaontology validation failed:\n" + "\n".join(self.violations))

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

    def import_nfx(self, path=None):
        """Import metaontology from an NFX file into the database."""
        data = nfx.read(path)

        for entry in data.get("nodes", []):
            node = Node(
                uuid=entry["nid"],
                labels=entry["labels"],
                properties=entry.get("properties", {}),
            )
            labels_str = ":".join(node.labels)
            query = f"""
            MERGE (n:{labels_str} {{`neuro.id`: $neuro_id}})
            SET n += $properties
            RETURN n
            """
            params = {"neuro_id": node.uuid, "properties": node.properties}
            self._nb.run_query(query, params)

        for rel in data.get("relationships", []):
            rel_type = rel["type"]
            query = f"""
            MATCH (a {{`neuro.id`: $from_id}})
            MATCH (b {{`neuro.id`: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            """
            params = {
                "from_id": rel["from"],
                "to_id": rel["to"],
                "properties": rel.get("properties", {}),
            }
            self._nb.run_query(query, params)
