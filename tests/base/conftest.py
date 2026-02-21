import pytest

from neuro.base import NeuroBase


@pytest.fixture
def nb():
    with NeuroBase() as nb:
        yield nb
