import os
import subprocess
import shutil

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

    if session.config.option.markexpr in ["", "integration"]:
        global PROCESS
        PROCESS = subprocess.Popen([
            "node",
            "../tw5/tiddlywiki.js",
            "../tw5/editions/neuro-test",
            "--listen",
            f"port={PORT}"
        ], stdout=subprocess.DEVNULL)


def pytest_sessionfinish(session, exitstatus):
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    try:
        PROCESS.kill()
    except NameError:
        pass
