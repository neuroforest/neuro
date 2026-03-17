import glob
import json
import os
from pathlib import Path
import shutil
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def test_file(tmp_path_factory):
    test_data_dir = Path(os.getenv("RESOURCES", "resources")) / "test"
    output_dir = Path(tempfile.mkdtemp(prefix="neuro-test-"))

    class TestFileLib:
        @staticmethod
        def create(subpath):
            test_path = output_dir / subpath
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
            # Check output first, then input data
            out_path = output_dir / subpath
            if out_path.exists():
                return str(out_path)
            test_path = test_data_dir / subpath
            if not test_path.exists():
                raise FileNotFoundError(f"Test data file not found: {test_path}")
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
            test_path = output_dir / subpath
            if test_path.exists():
                raise FileExistsError(f"Test data file exists: {test_path}")
            test_path.parent.mkdir(parents=True, exist_ok=True)
            return str(test_path)

    yield TestFileLib
    shutil.rmtree(output_dir, ignore_errors=True)
