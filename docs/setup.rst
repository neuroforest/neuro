Setup
=====

Edit file ``neuro/utils/SETTINGS.py``:

- Set the variables ``URL`` and ``PORT`` according to where your TiddlyWiki5 server instance is running.
- Set the variable ``NF_DIR`` to the absoulute path of the parent directory of ``neuro`` repository on the local file sistem. Setting the variable ``NF_DIR``  enables directory independence.

To run TiddlyWiki5 server locally:

::

     git clone https://github.com/Jermolene/TiddlyWiki5.git
     node TiddlyWiki5/tiddlywiki.js <wikifolder> --listen port=<port>

Where ``wikifolder`` is the pathname of your WikiFolder and ``port`` specifies where the instance will be served. 

OPTIONAL: For optimal performance and development purposes, the following file architecture is currently recommended:

::

	NeuroForest
	├── neuro
	└── storage
	| └── archive
	├── tw5 (or TiddlyWiki5)
	└── tw5-plugins