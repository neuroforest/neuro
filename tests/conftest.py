import os
import shutil


output_path = os.path.abspath("resources/test/output")


def pytest_sessionstart(session):
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)


def pytest_sessionfinish(session, exitstatus):
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    pass
