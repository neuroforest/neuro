# Ontology

The ontology module (`neuro.base.ontology`) defines the schema system for NeuroBase. It controls what node types exist, what properties they can have, and how nodes are validated before insertion.

## Graph Structure

The ontology is stored in Neo4j as a graph of its own, using three node types and five relationship types.

**Node types:**

- `OntologyNode` — defines a class/type (e.g. `Tiddler`, `Species`)
- `OntologyProperty` — defines a property (e.g. `created`, `neuro.id`)
- `OntologyRelationship` — defines a relationship type (e.g. `HAS_PROPERTY`)

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

**`Metaproperty`** — Represents a single property constraint for a node type. Holds the property label, owning node, property type (`DateTime`, `OntologyProperty`), and relationship type (`HAS_PROPERTY` or `REQUIRE_PROPERTY`). The `check()` method validates a value against the property type.

**`Metaproperties`** — A dict-like collection (`UserDict`) of `Metaproperty` objects keyed by property label. Ignores duplicate insertions. The `validate_properties()` method checks a node's properties against the collection, returning a `ValidationResult` with missing, undefined, and invalid properties.

**`ValidationResult`** — Accumulates validation violations. Supports two modes via `strict` flag:

- **strict** (default): missing, undefined, and invalid properties are all violations
- **lenient**: only missing and invalid properties are violations (undefined are allowed)

Supports `+` operator to merge results across multiple labels. Truthy when violations exist.

### Database-aware classes (require a `NeuroBase` instance)

**`OntologyNodeInfo`** — Queries and displays the full ontology profile for a node label: its lineage (`SUBCLASS_OF` chain), metaproperties (inherited through lineage), and relationships. Used by the NQL `info` command.

**`Validator`** — Base class for ontology validation. Provides `get_metaproperties(node_label)` which queries the ontology graph to resolve all properties (including inherited ones) for a given label.

**`ObjectValidator`** — Validates a `neuro.core.Object` against the ontology. Runs two checks:

1. `validate_labels()` — verifies each label exists as an `OntologyNode`
2. `validate_properties()` — checks properties against metaproperties for each valid label

Returns a `ValidationResult`.

**`OntologyValidator`**, **`MetaontologyValidator`** — Placeholder validators for validating the ontology structure itself. Not yet implemented.

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
                    ValidationResult
```

## Usage

```python
from neuro.base import NeuroBase
from neuro.base.ontology import OntologyNodeInfo, ObjectValidator

nb = NeuroBase()

# Inspect ontology for a label
info = OntologyNodeInfo(nb, "Species")
info.display()

# Validate an object before insertion
validator = ObjectValidator(nb, some_object)
result = validator.validate()
if result:
    print(result)  # shows violations
```
