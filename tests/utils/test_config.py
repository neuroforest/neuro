import pytest


def test_resolve_xdg_paths(monkeypatch):
    """An inherited NF_* never outranks the declared APP_NAME/ENV (issue #13)."""
    import os
    from neuro.utils import config

    for var in ("NF_CONFIG", "NF_DATA", "NF_STATE", "NF_CACHE"):
        monkeypatch.setenv(var, f"/stale/{var.lower()}")
    monkeypatch.setenv("APP_NAME", "sirin")
    monkeypatch.setenv("ENV", "PRODUCTION")

    config.resolve_xdg_paths()
    assert os.environ["NF_CONFIG"].endswith("/sirin")
    assert os.environ["NF_DATA"].endswith("/sirin")
    assert os.environ["NF_STATE"].endswith("/sirin/production")
    assert os.environ["NF_CACHE"].endswith("/sirin/production")

    # A second pass under a different ENV re-namespaces rather than sticking.
    monkeypatch.setenv("ENV", "TESTING")
    config.resolve_xdg_paths()
    assert os.environ["NF_DATA"].endswith("/sirin/testing")
    assert os.environ["NF_STATE"].endswith("/sirin/testing")


class TestUtils:
    pytestmark = pytest.mark.integration

    def test_config(self):
        import os
        assert os.getenv("HOST") == "127.0.0.1"
        assert os.getenv("ENV") == "TESTING"
        assert os.getenv("NCBI_API_KEY")

    def test_internal_utils(self):
        from neuro.utils import internal_utils
        neuro_path = internal_utils.get_path("neuro")
        assert neuro_path.is_absolute() is True and neuro_path.exists() is True
