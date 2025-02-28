class TestUtils:
    def test_config(self):
        import os
        from neuro.utils import config
        config.load_env_files()
        assert os.path.exists(os.getenv("NEURO")) is True

    def test_internal_utils(self):
        import os
        from neuro.utils import internal_utils
        neuro_path = internal_utils.get_path("neuro")
        assert os.path.isabs(neuro_path) is True
