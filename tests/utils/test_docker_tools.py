"""
Unit tests for the package neuro.utils.docker_tools.
"""
import os
import stat

import pytest

from neuro.utils import docker_tools
from neuro.utils.docker_tools import Container


class TestDockerTools:
    def test_docker_tools(self):
        from neuro.utils import docker_tools  # noqa: F401


@pytest.mark.unit
class TestBackupLayout:
    """A backup is a directory with the data volume; the container image is the
    mark of a full one."""

    def test_data_only_is_valid(self, tmp_path):
        (tmp_path / "data.tar.gz").write_bytes(b"x")
        assert Container.is_valid_backup(str(tmp_path))
        assert Container.backup_kind(str(tmp_path)) == "data"

    def test_full_backup(self, tmp_path):
        (tmp_path / "data.tar.gz").write_bytes(b"x")
        (tmp_path / "container.tar").write_bytes(b"x")
        (tmp_path / "logs.tar.gz").write_bytes(b"x")
        assert Container.backup_kind(str(tmp_path)) == "full"

    def test_container_alone_is_not_a_backup(self, tmp_path):
        (tmp_path / "container.tar").write_bytes(b"x")
        assert not Container.is_valid_backup(str(tmp_path))
        assert Container.backup_kind(str(tmp_path)) is None


@pytest.mark.unit
class TestStreamToFile:
    """The producer's stdout lands in a file this process owns, 0600; a failed
    producer leaves nothing behind."""

    def test_writes_owner_only(self, tmp_path):
        dest = tmp_path / "out.bin"
        Container._stream_to_file(["sh", "-c", "printf abc"], str(dest))
        assert dest.read_bytes() == b"abc"
        st = os.stat(dest)
        assert st.st_uid == os.getuid()
        assert stat.S_IMODE(st.st_mode) == 0o600

    def test_failed_producer_leaves_no_file(self, tmp_path):
        dest = tmp_path / "out.bin"
        with pytest.raises(Exception, match="exited 3"):
            Container._stream_to_file(["sh", "-c", "printf partial; exit 3"], str(dest))
        assert not dest.exists()

    def test_refuses_to_overwrite(self, tmp_path):
        dest = tmp_path / "out.bin"
        dest.write_bytes(b"keep")
        with pytest.raises(FileExistsError):
            Container._stream_to_file(["sh", "-c", "printf new"], str(dest))
        assert dest.read_bytes() == b"keep"


@pytest.mark.unit
def test_restore_container_needs_a_full_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE", str(tmp_path))
    c = Container(name="x", archive=str(tmp_path))
    c.backup_location = str(tmp_path / "x-2026-01-01_00-00-00")
    os.makedirs(c.backup_location)
    with pytest.raises(ValueError, match="Not a full backup"):
        c.restore_container()
    assert docker_tools is not None
