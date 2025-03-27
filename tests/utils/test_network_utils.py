class TestNetworkUtils:
    def test_is_port_in_use(self):
        import os
        port = os.getenv("TEST_PORT")
        from neuro.utils import network_utils
        assert network_utils.is_port_in_use(str(port)) is True
        assert network_utils.is_port_in_use(int(port)) is True
