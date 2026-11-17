"""
Unit tests for neuro.utils.internal_utils - PLUGINS-style path lists.
"""

import os

import pytest

from neuro.utils import exceptions, internal_utils

pytestmark = pytest.mark.unit


class TestGetPathList:
    def test_get_path_list(self, tmp_path, monkeypatch, caplog):
        (tmp_path / "a").mkdir()
        monkeypatch.setenv("APP_DIR", str(tmp_path))
        monkeypatch.setenv("PLUGINS", f"a{os.pathsep}missing{os.pathsep}{tmp_path / 'a'}")
        paths = internal_utils.get_path_list("PLUGINS")
        assert paths == [(tmp_path / "a").resolve(), (tmp_path / "a").resolve()]
        assert "missing" in caplog.text

    def test_get_path_list_strict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_DIR", str(tmp_path))
        monkeypatch.setenv("PLUGINS", "missing")
        with pytest.raises(exceptions.InvalidPath):
            internal_utils.get_path_list("PLUGINS", strict=True)

    def test_get_path_list_expands_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_DIR", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".nf").mkdir()
        monkeypatch.setenv("PLUGINS", "~/.nf")
        assert internal_utils.get_path_list("PLUGINS") == [(tmp_path / ".nf").resolve()]

    def test_missing_path_list(self, tmp_path, monkeypatch):
        (tmp_path / "a").mkdir()
        monkeypatch.setenv("APP_DIR", str(tmp_path))
        monkeypatch.setenv("PLUGINS", f"a{os.pathsep}gone")
        assert internal_utils.missing_path_list("PLUGINS") == [tmp_path / "gone"]
