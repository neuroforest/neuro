import os
import subprocess
import shutil

from neuro.utils import network_utils

from .helper import PORT


PROCESS: subprocess.Popen


def pytest_sessionstart(session):
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    output_path = os.path.abspath("resources/test/output")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)

    # Restore submodules
    os.system("git submodule foreach git checkout -f origin/master")
    os.system("git submodule foreach git clean -fd")

    if session.config.option.markexpr in ["", "integration"]:
        global PROCESS
        PROCESS = subprocess.Popen([
            "node",
            "tw5/tiddlywiki.js",
            "tw5/editions/neuro-test",
            "--listen",
            f"port={PORT}",
            "readers=(anon)",
            "writers=(anon)"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    network_utils.wait_for_socket("127.0.0.1", PORT)


def pytest_sessionfinish(session, exitstatus):
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    try:
        PROCESS.kill()
    except NameError:
        pass
