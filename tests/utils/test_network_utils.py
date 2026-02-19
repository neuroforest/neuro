import socket

import pytest


@pytest.fixture
def dummy_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
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


def test_wait_for_socket_connects(dummy_port):
    from neuro.utils import network_utils
    network_utils.wait_for_socket("127.0.0.1", dummy_port, timeout=5)


def test_wait_for_socket_timeout():
    from neuro.utils import network_utils
    free = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()  # port is free — nothing listening
    with pytest.raises(TimeoutError):
        network_utils.wait_for_socket("127.0.0.1", port, timeout=0.3)
