# NFX – NeuroForest Exchange

Graph interchange format used by `nb.nodes.export_nfx()` and `nb.nodes.import_nfx()`.

- Extension: `.nfx`
- MIME: `application/nfx+json`

## Structure

```json
{
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
      "properties": {}
    }
  ]
}
```

## Fields

### Node

| Field        | Type     | Description                          |
|--------------|----------|--------------------------------------|
| `nid`        | `string` | UUID identifying the node (stored as `neuro.id` in Neo4j, not duplicated in `properties`) |
| `labels`     | `list`   | Neo4j labels (e.g. `["Tiddler"]`)    |
| `properties` | `dict`   | Node properties (excludes `neuro.id`) |

### Relationship

| Field        | Type     | Description                                  |
|--------------|----------|----------------------------------------------|
| `from`       | `string` | `nid` of the source node                     |
| `to`         | `string` | `nid` of the target node                     |
| `type`       | `string` | Relationship type (e.g. `"PARENT_OF"`)       |
| `properties` | `dict`   | Relationship properties (may be empty)       |

## Behavior

- **Export** writes all matched nodes and inter-node relationships to the file. Nodes can be filtered by label and properties.
- **Import** reads the file and merges each node on `neuro.id`, then merges each relationship between the referenced nodes. Existing data is updated, not duplicated.
