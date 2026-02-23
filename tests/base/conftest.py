import pytest

from neuro.base import NeuroBase
from neuro.utils.internal_utils import get_path


@pytest.fixture
def nb():
    with NeuroBase() as nb:
        nb.clear(confirm=True)
        yield nb


@pytest.fixture
def nb_meta(nb):
    path = get_path("resources") / "metaontology.nfx"
    nb.metaontology.import_nfx(path)
    yield nb
