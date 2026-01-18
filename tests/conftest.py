import os
import subprocess
import shutil

from neuro.utils import config  # noqa: F401
from neuro.utils import exceptions, network_utils

from .helper import create_and_run_wiki_folder


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
        PROCESS = create_and_run_wiki_folder("universal", test_port)

    network_utils.wait_for_socket(os.getenv("HOST"), test_port)


def pytest_sessionfinish(session, exitstatus):
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    try:
        PROCESS.kill()
    except NameError:
        pass
