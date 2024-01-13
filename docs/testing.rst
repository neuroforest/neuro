Testing
=======

The tests are in the folder ``tests``.

The data is in the folder ``data/tests``. There are 3 subdirectories:

* ``input`` - files used as input for tests
* ``results`` - files (or their text) that are used as a reference
* ``output`` - files that are produced during a test

To run all tests use command

::

	venv/bin/pytest tests

To run only integration tests, use command

::

	venv/bin/pytest tests -m "integration"
