import os
import shutil


def pytest_sessionstart(session):
    output_path = os.path.abspath("resources/test/output")
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)
