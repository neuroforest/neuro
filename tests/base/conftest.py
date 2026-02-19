import pytest

from neuro.base.api import NeuroBase


@pytest.fixture
def nb():
    nb = NeuroBase()
    yield nb
    nb.close()
