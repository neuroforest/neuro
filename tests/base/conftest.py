from pathlib import Path

import pytest

from neuro.base import NeuroBase
from neuro.utils.internal_utils import get_path


def pytest_collection_modifyitems(items):
    for item in items:
        if Path(__file__).parent in Path(item.fspath).parents:
            if not any(m.name == "unit" for m in item.iter_markers()):
                item.add_marker(pytest.mark.integration)


@pytest.fixture
def nb():
    with NeuroBase() as nb:
        nb.clear(confirm=True)
        yield nb


@pytest.fixture
def nb_meta(nb):
    path = get_path("resources") / "metaontology.nfx"
    nb.nodes.import_nfx(path)
    yield nb
