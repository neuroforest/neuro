# NFX – NeuroForest Exchange

Graph interchange format for nodes and relationships.

- Extension: `.nfx`
- MIME: `application/nfx+json`

## Structure

```json
{
  "name": "Graph Name",
  "description": "Optional description",
  "version": "1.0",
  "nodes": [
    {
      "nid": "<neuro.id>",
      "labels": ["Label1", "Label2"],
      "properties": {
        "title": "Example",
        "neuro.role": "taxon.species"
      }
    }
  ],
  "relationships": [
    {
      "from": "<neuro.id>",
      "to": "<neuro.id>",
      "type": "PARENT_OF",
      "properties": {"weight": 1}
    }
  ]
}
```

## Fields

### Top-level

| Field         | Type     | Description                          |
|---------------|----------|--------------------------------------|
| `name`        | `string` | Name of the export (e.g. `"Metaontology"`) |
| `description` | `string` | Human-readable description           |
| `version`     | `string` | Version identifier                   |

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
nb.nodes.import_nfx(path)
```

Reads the file, validates each node against the ontology, and merges on `neuro.id`. Relationships are merged between the referenced nodes. Existing data is updated, not duplicated.

## Low-level I/O

The `neuro.base.nfx` module provides pure read/write functions with no database dependency:

- `nfx.read(path)` — returns the parsed JSON dict
- `nfx.write(path, nodes, relationships, name="", description="", version="")` — writes to file, returns the data dict
