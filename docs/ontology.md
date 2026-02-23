# Ontology

The ontology module (`neuro.base.ontology`) defines the schema system for NeuroBase. It controls what node types exist, what properties they can have, and how nodes are validated before insertion.

## Graph Structure

The ontology is stored in Neo4j as a graph of its own, using three node types and five relationship types.

**Node types:**

- `OntologyNode` - defines a class/type (e.g. `Tiddler`, `Species`)
- `OntologyProperty` - defines a property (e.g. `created`, `neuro.id`)
- `OntologyRelationship` - defines a relationship type (e.g. `HAS_PROPERTY`)

**Relationships:**

```
(OntologyNode)-[:SUBCLASS_OF]->(OntologyNode)
    Class hierarchy. Traversed with variable-length paths (*0..).

(OntologyNode)-[:HAS_PROPERTY]->(OntologyProperty)
    Optional property for a node type.

(OntologyNode)-[:REQUIRE_PROPERTY]->(OntologyProperty)
    Required property for a node type.

(OntologyNode)-[:HAS_RELATIONSHIP]->(OntologyRelationship)
    Declares a relationship type on a node.

(OntologyRelationship)-[:HAS_TARGET]->(OntologyNode)
    Specifies the target node type for a relationship.
```

Properties are inherited through `SUBCLASS_OF` chains. If `Species` is a subclass of `Tiddler`, it inherits all of `Tiddler`'s required and optional properties.

## Classes

### Data classes (no database access)

**`Metaproperty`** - Represents a single property constraint for a node type. Holds the property label, owning node, property type (`DateTime`, `OntologyProperty`), and relationship type (`HAS_PROPERTY` or `REQUIRE_PROPERTY`). The `check()` method validates a value against the property type.

**`Metaproperties`** - A dict-like collection (`UserDict`) of `Metaproperty` objects keyed by property label. Ignores duplicate insertions. The `validate_properties()` method checks a node's properties against the collection, returning a `Violations` object with missing, undefined, and invalid properties.

**`Violations`** - Collects ontology violations found during validation. Truthy when violations exist, falsy when empty (no violations). Contains four lists:

- `undefined_labels` - labels not found as `OntologyNode` in the graph
- `missing_properties` - required properties (`REQUIRE_PROPERTY`) that are absent
- `undefined_properties` - properties present on the node but not defined in the ontology
- `invalid_properties` - properties with values that fail type checks

Supports two modes via `strict` flag:

- **strict** (default): all four lists count as violations
- **lenient**: `undefined_properties` are ignored (only missing, invalid, and undefined labels count)

Supports `+` operator to merge results across multiple labels.

### Database-aware classes (require a `NeuroBase` instance)

**`Ontology`** - Accessor mounted on `NeuroBase` as `nb.ontology`. Provides:

- `is_valid_node(node)` - validates a node's labels and properties against the ontology, returns a `Violations` object
- `info(label)` - returns an `OntologyNodeInfo` for the given label

**`OntologyNodeInfo`** - Queries and displays the full ontology profile for a node label: its lineage (`SUBCLASS_OF` chain), metaproperties (inherited through lineage), and relationships. Used by the NQL `info` command.

**`Validator`** - Base class for ontology validation. Provides `get_metaproperties(node_label)` which queries the ontology graph to resolve all properties (including inherited ones) for a given label.

**`ObjectValidator`** - Validates a `neuro.core.Object` against the ontology. Runs two checks:

1. `validate_labels()` - verifies each label exists as an `OntologyNode`
2. `validate_properties()` - checks properties against metaproperties for each valid label

Returns a `Violations` object.

**`OntologyValidator`**, **`MetaontologyValidator`** - Placeholder validators for validating the ontology structure itself. Not yet implemented.

## Validation Flow

```
Object(labels, properties)
    │
    ▼
ObjectValidator.validate()
    │
    ├── validate_labels()
    │       For each label:
    │           MATCH (n:OntologyNode {label: $label})
    │           → undefined_labels if not found
    │
    └── validate_properties()
            For each valid label:
                Validator.get_metaproperties(label)
                    → resolves SUBCLASS_OF chain
                    → collects HAS_PROPERTY + REQUIRE_PROPERTY
                Metaproperties.validate_properties(object.properties)
                    → missing_properties (required but absent)
                    → undefined_properties (present but not in schema)
                    → invalid_properties (wrong type)
                        │
                        ▼
                    Violations
```

## Usage

```python
from neuro.base import NeuroBase

with NeuroBase() as nb:
    # Inspect ontology for a label
    nb.ontology.info("Species").display()

    # Validate a node before insertion
    violations = nb.ontology.is_valid_node(node)
    if violations:
        print(violations)  # shows undefined labels, missing/invalid properties
```

`nb.nodes.put(node)` calls `is_valid_node` automatically and raises `ValueError` if violations are found.
