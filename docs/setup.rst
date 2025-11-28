Setup
----

Settings
^^^^

Create file ``.env`` using ``.env.defaults`` as the template.

- Set the variable ``NF_DIR`` to the absolute path of the parent directory of ``neuro`` repository on the local file sistem. Setting the variable ``NF_DIR`` enables independence of the working directory.

TiddlyWiki5
^^^^

To run TiddlyWiki5 server locally:

::

    git clone https://github.com/Jermolene/TiddlyWiki5.git
    node TiddlyWiki5/tiddlywiki.js <wikifolder> --listen port=<port>

Where ``wikifolder`` is the pathname of your WikiFolder and ``port`` specifies where the instance will be served. 

Architecture
^^^^

OPTIONAL: For optimal performance and development purposes, the following file architecture is currently recommended:

::

    NeuroForest
    ├── desktop
    ├── neuro
    └── storage
    | └── archive
    ├── tw5
    └── tw5-plugins