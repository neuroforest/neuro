"""
NeuroBase.clear refuses a base the env-file chain did not declare (INC-2026-007).

No database: the guard runs before the DETACH DELETE is sent, so a recording
run_query stands in for the driver.
"""

import pytest

from neuro.base import NeuroBase
from neuro.utils import config

pytestmark = pytest.mark.unit

DECLARED_URI = "bolt://127.0.0.1:7687"


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """A repo .env and a TESTING override, as nte resolves them."""
    app, cfg = tmp_path / "app", tmp_path / "cfg"
    app.mkdir()
    cfg.mkdir()
    (app / ".env").write_text(f"BASE_NAME=neurobase\nNEO4J_URI={DECLARED_URI}\n")
    (cfg / "env.testing").write_text("BASE_NAME=test-nbase\n")
    for key in config.IDENTITY_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_DIR", str(app))
    monkeypatch.setenv("NF_CONFIG", str(cfg))
    monkeypatch.setenv("ENV", "TESTING")
    return monkeypatch


def _base(uri=DECLARED_URI):
    nb = NeuroBase.__new__(NeuroBase)
    nb._uri = uri
    nb.sent = []
    nb.run_query = lambda query, parameters=None: nb.sent.append(query)
    return nb


def _refused(nb, key):
    with pytest.raises(RuntimeError, match=key):
        nb.clear(confirm=True)
    assert nb.sent == []


def test_declared_base_is_cleared(chain):
    chain.setenv("BASE_NAME", "test-nbase")
    chain.setenv("NEO4J_URI", DECLARED_URI)
    nb = _base()
    nb.clear(confirm=True)
    assert any("DETACH DELETE" in q for q in nb.sent)


def test_inherited_base_name_is_refused(chain):
    """The runner's APP_NAME reached the child: its BASE_NAME rode along."""
    chain.setenv("BASE_NAME", "sirin")
    chain.setenv("NEO4J_URI", DECLARED_URI)
    _refused(_base(), "BASE_NAME")


def test_inherited_uri_under_the_declared_name_is_refused(chain):
    """The name is re-declared by env.testing while the URI still reaches production."""
    chain.setenv("BASE_NAME", "test-nbase")
    chain.setenv("NEO4J_URI", "bolt://127.0.0.1:4307")
    _refused(_base("bolt://127.0.0.1:4307"), "NEO4J_URI")


def test_a_key_no_file_declares_is_refused(chain):
    """A pinned store id is production-only; arriving here it can only be inherited."""
    chain.setenv("BASE_NAME", "test-nbase")
    chain.setenv("NEO4J_URI", DECLARED_URI)
    chain.setenv("NEO4J_STORE_ID", "a4bf35fa")
    _refused(_base(), "NEO4J_STORE_ID")


def test_an_explicit_uri_config_does_not_name_is_refused(chain):
    chain.setenv("BASE_NAME", "test-nbase")
    chain.setenv("NEO4J_URI", DECLARED_URI)
    _refused(_base("bolt://10.0.0.5:7687"), "NEO4J_URI")


def test_confirm_is_still_required(chain):
    with pytest.raises(ValueError):
        _base().clear()
