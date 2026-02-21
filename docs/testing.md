# Testing

**Testing data**

The data is in the folder `data/tests`. There are 3 subdirectories:

* `input` - files used as input for tests
* `results` - files (or their text) that are used as a reference
* `output` - files that are produced during a test

**Environment variables**

The default variable names used for testing are stored in file `.env`. Variables in this file can be overridden by creating the file `.env.testing` in the root directory.

**Running tests**

The tests are stored in the folder `tests`.

To run all tests use command

```
venv/bin/pytest tests
```
