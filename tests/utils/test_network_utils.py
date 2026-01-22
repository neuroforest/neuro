import socket

import pytest


@pytest.fixture
def dummy_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("localhost", 0))
    sock.listen()
    port = sock.getsockname()[1]
    yield port
    sock.close()


def test_is_port_in_use(dummy_port):
    from neuro.utils import network_utils
    assert network_utils.is_port_in_use(dummy_port) is True


def test_release_port(dummy_port):
    import shutil
    assert shutil.which("killport") is not None
