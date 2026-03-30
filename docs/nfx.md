# NFX – NeuroForest Exchange

Graph interchange format for nodes and relationships.

- Extension: `.nfx`
- MIME: `application/nfx+json`

## Structure

```json
{
  "name": "namespace/name",
  "description": "Optional description",
  "version": "1.0",
  "dependencies": ["namespace/dep@1.0"],
  "nodes": [
    {
      "nid": "<nid>",
      "labels": ["Label1", "Label2"],
      "properties": {
        "title": "Example",
        "neuro.role": "taxon.species"
      }
    }
  ],
  "relationships": [
    {
      "from": "<nid>",
      "to": "<nid>",
      "type": "PARENT_OF",
      "properties": {"weight": 1}
    }
  ]
}
```

## Fields

### Top-level

| Field          | Type     | Description                                                    |
|----------------|----------|----------------------------------------------------------------|
| `name`         | `string` | Qualified name: `namespace/name` (e.g. `neuroforest/metaontology`) |
| `description`  | `string` | Human-readable description                                     |
| `version`      | `string` | Version identifier                                             |
| `dependencies` | `list`   | Required ontologies: `namespace/name@version` (e.g. `["neuroforest/metaontology@1.2"]`) |

### Node

| Field        | Type     | Description                          |
|--------------|----------|--------------------------------------|
| `nid`        | `string` | UUID identifying the node (stored as `neuro.id` in Neo4j) |
| `labels`     | `list`   | Neo4j labels (e.g. `["Tiddler"]`)    |
| `properties` | `dict`   | Node properties (excludes `neuro.id`). Omitted when empty. |

### Relationship

| Field        | Type     | Description                                  |
|--------------|----------|----------------------------------------------|
| `from`       | `string` | `nid` of the source node                     |
| `to`         | `string` | `nid` of the target node                     |
| `type`       | `string` | Relationship type (e.g. `"PARENT_OF"`)       |
| `properties` | `dict`   | Relationship properties. Omitted when empty. |

## API

### Export

```python
# Export nodes, optionally filtered by label and properties
nb.nodes.export_nfx(path, label="Tiddler", name="My Export")

# Export the metaontology
nb.metaontology.export_nfx(path)
```

`export_nfx` writes matched nodes and their inter-node relationships to the file. `neuro.id` is extracted to the `nid` field and removed from `properties`.

### Import

```python
# Import nodes with ontology validation
nb.nodes.import_nfx(path)

# Import metaontology (bypasses validation — schema defines validation rules)
nb.metaontology.import_nfx(path)
```

Reads the file and merges on `neuro.id`. Relationships are merged between the referenced nodes. Existing data is updated, not duplicated. `nodes.import_nfx` validates each node against the ontology; `metaontology.import_nfx` uses direct Cypher MERGE.

## Low-level I/O

The `neuro.base.nfx` module provides pure read/write functions with no database dependency:

- `nfx.read(path)` — returns the parsed JSON dict
- `nfx.write(path, nodes, relationships, name="", description="", version="", dependencies=None)` — writes to file, returns the data dict
