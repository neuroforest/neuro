import pytest


pytestmark = pytest.mark.integration


class TestUtils:
    def test_config(self):
        import os
        assert os.getenv("HOST") == "127.0.0.1"
        assert os.getenv("ENVIRONMENT") == "TESTING"
        assert os.getenv("NCBI_API_KEY")

    def test_internal_utils(self):
        from neuro.utils import internal_utils
        neuro_path = internal_utils.get_path("neuro")
        assert neuro_path.is_absolute() is True and neuro_path.exists() is True
