# neuro
`neuro` is a Python package that features:

- <a href="https://neo4j.com" target="_blank">Neo4j</a> as the graph database
- <a href="https://tiddlywiki.com" target="_blank">TiddlyWiki5</a> as the user interface
- API to the database and the user interface
- integrations with <a href="https://www.ncbi.nlm.nih.gov/taxonomy" target="_blank">NCBI Taxonomy</a>, <a href="https://www.wikidata.org" target="_blank">WikiData</a>, <a href="https://www.gbif.org" target="_blank">GBIF</a>, <a href="https://www.inaturalist.org" target="_blank">iNaturalist</a>, and <a href="https://www.zotero.org/" target="_blank">Zotero</a>
- file and data management tools
- command-line interface 

### Requirements

- git
- Python 3.13
- node.js
- NW.js
- TiddlyWiki5
- Neo4j

### Install

```bash
git clone https://github.com/neuroforest/neuro.git
cd neuro
python3 -m venv venv
venv/bin/pip install .
venv/bin/neuro --help
```

Edit configuration in ``.env`` (see ``docs/setup.rst`` for more info)

### Test

```bash
venv/bin/pytest tests
```

More info about testing: ``docs/testing.rst``
