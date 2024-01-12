# neuro
`neuro` is a Python package that features:

- an interface to <a href="https://tiddlywiki.com" target="_blank">TiddlyWiki5</a> API
- file and data management utilities
- wrappers for <a href="https://www.wikidata.org" target="_blank">WikiData</a>, <a href="https://www.inaturalist.org" target="_blank">iNaturalist</a> and <a href="https://www.gbif.org" target="_blank">GBIF</a>
- command-line interface 

### Requirements

- git
- Python 3.6 or higher
- node.js
- TiddlyWiki5 server

### Install

Edit settings in ``neuro/utils/SETTINGS.py`` (see ``docs/setup.rst`` for more info)

```bash
git clone https://github.com/neuroforest/neuro.git
cd neuro
python3 -m venv venv
venv/bin/pip install .
venv/bin/neuro --help
```

### Test

```bash
venv/bin/neuro test
```

More info about testing: ``docs/testing.rst``
