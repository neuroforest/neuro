import glob
import json
import os
from pathlib import Path
import shutil

import pytest


def pytest_sessionstart(session):
    output_path = Path(os.getenv("RESOURCES", "resources")) / "test" / "output"
    shutil.rmtree(output_path, ignore_errors=True)
    os.makedirs(output_path)


@pytest.fixture(scope="session", autouse=True)
def test_file():
    test_data_dir = Path(os.getenv("RESOURCES", "resources")) / "test"

    class TestFileLib:
        @staticmethod
        def create(subpath):
            test_path = test_data_dir / subpath
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.touch(exist_ok=False)
            return str(test_path)

        @staticmethod
        def dict(subpath):
            json_path = TestFileLib.get(subpath)
            with open(json_path) as f:
                json_text = f.read()
            return json.loads(json_text)

        @staticmethod
        def get(subpath):
            test_path = test_data_dir / subpath
            if not test_path.exists():
                raise FileNotFoundError(f"Test data file not found: {test_path}")
            else:
                return str(test_path)

        @staticmethod
        def multi(subpath):
            test_path = test_data_dir / subpath
            test_paths = glob.glob(str(test_path) + "*")
            test_paths.sort()
            if len(test_paths) == 0:
                raise FileNotFoundError(f"Test data file not found: {test_path}")
            else:
                return test_paths

        @staticmethod
        def path(subpath):
            test_path = test_data_dir / subpath
            if test_path.exists():
                raise FileExistsError(f"Test data file exists: {test_path}")
            else:
                return str(test_path)

    yield TestFileLib
