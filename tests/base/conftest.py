import pytest

from neuro.base import NeuroBase


@pytest.fixture
def nb():
    nb = NeuroBase()
    yield nb
    nb.close()
