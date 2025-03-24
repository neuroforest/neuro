import os
import subprocess
import shutil

from neuro.utils import network_utils, exceptions


PROCESS: subprocess.Popen


def pytest_sessionstart(session):
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    test_port = os.getenv("TEST_PORT")
    output_path = os.path.abspath("resources/test/output")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)

    if network_utils.is_port_in_use(test_port):
        raise exceptions.PortInUse(test_port)

    if session.config.option.markexpr in ["", "integration"]:
        global PROCESS
        PROCESS = subprocess.Popen([
            "node",
            "tw5/tiddlywiki.js",
            "tw5/editions/neuro-test",
            "--listen",
            f"port={test_port}",
            "readers=(anon)",
            "writers=(anon)"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    network_utils.wait_for_socket(os.getenv('URL'), test_port)


def pytest_sessionfinish(session, exitstatus):
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    try:
        PROCESS.kill()
    except NameError:
        pass
