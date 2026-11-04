"""
Tools for Docker container management.
"""

import json
import logging
import os
import shutil
import subprocess

import docker

from neuro.core import Dir
from neuro.utils import internal_utils, time_utils


def verify_access():
    """Check that Docker is running and the current user can connect."""
    result = subprocess.run(
        ["docker", "info"], capture_output=True, text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "permission denied" in stderr:
            raise SystemExit(
                "Permission denied connecting to Docker.\n"
                "Add your user to the docker group:\n\n"
                "  sudo usermod -aG docker $USER\n\n"
                "Then log out and back in."
            )
        raise SystemExit(
            "Docker daemon is not running.\n"
            "Start it with:\n\n"
            "  sudo systemctl start docker"
        )


class Container:
    def __init__(self, name=None, archive=None):
        self.name = name
        self.instant = str()
        self.archive = archive or internal_utils.get_path("archive", create_if_missing=True) / "base"
        os.makedirs(self.archive, exist_ok=True)
        self.backup_location = str()
        self.dirty = {
            "container": list(),
            "image": list(),
            "volume": list()
        }

    @staticmethod
    def is_valid_backup(b):
        """A backup is a directory holding the data volume; the rest is optional.

        `container.tar` and `logs.tar.gz` ride along only in a full backup
        a restore needs the data volume alone, the container is
        recreated from the compose image.
        """
        return os.path.isfile(f"{b}/data.tar.gz")

    @staticmethod
    def backup_kind(b):
        """'full' when the container image is in the backup, 'data' when only the
        volume is, None when it is not a backup at all."""
        if not Container.is_valid_backup(b):
            return None
        return "full" if os.path.isfile(f"{b}/container.tar") else "data"

    def backup(self, full=False):
        """
        Back up the container's data volume into a new archive directory.

        Default is the data volume only; `full` adds the container image and the
        logs volume. Every file is written by this process (owner = the caller,
        mode 0600), never by a container onto a bind mount, so nothing in the
        archive is root-owned or world-readable.
        """
        if not self.name:
            raise ValueError("Container name not provided.")
        self.instant = time_utils.MOMENT_4
        self.backup_location = f"{self.archive}/{self.name}-{self.instant}"
        os.makedirs(self.backup_location)
        self.backup_data()
        if full:
            self.backup_logs()
            self.backup_container()

    def _mounted_volume(self, destination):
        """Name of the named volume mounted at `destination` in the container,
        None when nothing is mounted there."""
        result = subprocess.run([
            "docker",
            "inspect",
            self.name,
            "--format", "{{json .Mounts}}"
        ], capture_output=True, text=True)
        try:
            mounts = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise Exception(f"Container not found: {self.name}")
        for mount in mounts:
            if mount["Destination"] == destination and mount.get("Type") == "volume":
                return mount["Name"]
        return None

    @staticmethod
    def _stream_to_file(cmd, dest):
        """Run `cmd` and write its stdout to `dest`, created 0600 by this process.

        The producer's exit status is checked: a failed producer leaves no file
        behind, so a half-written archive can never be mistaken for a backup.
        """
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                shutil.copyfileobj(proc.stdout, out, length=1 << 20)
                _, stderr = proc.communicate()
        except BaseException:
            os.unlink(dest)
            raise
        if proc.returncode != 0:
            os.unlink(dest)
            raise Exception(
                f"Backup error: {' '.join(cmd[:2])} exited {proc.returncode}: "
                f"{stderr.decode(errors='replace').strip()}"
            )

    def _tar_volume(self, destination, filename):
        """Tar a named volume mounted at `destination` in the (stopped) container
        straight into `<backup_location>/<filename>`. Returns False when the
        container mounts nothing there."""
        volume = self._mounted_volume(destination)
        if not volume:
            return False
        logging.debug(f"Found {destination} volume: {volume}")
        self._stream_to_file([
            "docker",
            "run", "--rm",
            "-v", f"{volume}:/src:ro",
            "alpine", "sh", "-c",
            "cd /src && tar cz ."
        ], f"{self.backup_location}/{filename}")
        logging.debug(f"Archived {destination} to {self.backup_location}/{filename}")
        return True

    def list_backups(self):
        archive_dir = Dir(self.archive)
        backups = archive_dir.get_children()
        valid_backups = list()
        for b in backups:
            if self.is_valid_backup(b):
                if self.name and self.name in b.rsplit("/", 1)[1]:
                    valid_backups.append(b)
                elif not self.name:
                    valid_backups.append(b)

        for b in valid_backups:
            print(b.replace(f"{self.archive}/", ""))

    def backup_data(self):
        """The data volume (/data) → data.tar.gz.

        Read straight from the volume, mounted read-only: the container is stopped
        before a backup, so the volume is quiescent and the scratch copy the old
        path made (cp -a into a throw-away volume, then tar) only doubled the I/O
        and the time the base was down.
        """
        if not self._tar_volume("/data", "data.tar.gz"):
            raise Exception(f"Backup error: {self.name} mounts no volume at /data.")

    def backup_logs(self):
        """The logs volume (/logs) → logs.tar.gz; skipped when the container has none."""
        if not self._tar_volume("/logs", "logs.tar.gz"):
            logging.debug(f"{self.name} mounts no volume at /logs - no logs.tar.gz")

    def backup_container(self):
        backup_name = f"{self.name}:{self.instant}"
        result = subprocess.run([
            "docker",
            "commit",
            self.name,
            backup_name
        ], capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Backup error: docker commit failed: {result.stderr.strip()}")
        logging.debug(f"Saved {self.name} to {backup_name}")

        # Verify
        result = subprocess.run([
            "docker",
            "images",
            "--format", "{{.Repository}}:{{.Tag}}"
        ], capture_output=True, text=True)
        if f"{self.name}:{self.instant}" not in result.stdout.strip().split("\n"):
            raise Exception(f"Backup error: image {backup_name} not found.")
        self.dirty["image"].append(backup_name)

        # Archive container - to stdout, written by this process (0600)
        self._stream_to_file(
            ["docker", "save", backup_name],
            f"{self.backup_location}/container.tar",
        )

    def restore(self, backup_location):
        if self.is_valid_backup(backup_location):
            self.backup_location = backup_location
        else:
            expanded_location = f"{self.archive}/{backup_location}"
            if self.is_valid_backup(expanded_location):
                self.backup_location = expanded_location
            else:
                raise ValueError(f"Backup location invalid: {backup_location}")

        self.name, self.instant = self.backup_location.rsplit("/", 1)[1].split("-", 1)

        self.restore_data()
        if self.backup_kind(self.backup_location) == "full":
            self.restore_container()

    def restore_data(self, target_volume=None):
        """Restore backup data into a volume. Clears existing contents first.

        If target_volume is given, restores into that volume.
        Otherwise creates a new volume named {name}-{instant} and tracks it for cleanup.
        """
        logging.debug("Restoring data")
        if target_volume:
            volume_name = target_volume
        else:
            volume_name = f"{self.name}-{self.instant}"
            self.dirty["volume"].append(volume_name)
        subprocess.run([
            "docker",
            "run", "--rm",
            "-v", f"{volume_name}:/data",
            "-v", f"{self.backup_location}:/backup",
            "alpine", "sh", "-c",
            "find /data -mindepth 1 -delete && cd /data && tar xzf /backup/data.tar.gz"
        ], capture_output=True)

    def restore_container(self):
        """Load the saved container image - only a full backup carries one."""
        if not os.path.isfile(f"{self.backup_location}/container.tar"):
            raise ValueError(f"Not a full backup (no container.tar): {self.backup_location}")
        logging.debug("Restoring container as image")
        subprocess.run([
            "docker",
            "load",
            "-i", f"{self.backup_location}/container.tar"
        ], capture_output=True)
        self.dirty["image"].append(f"{self.name}:{self.instant}")

    def run_restored_neo4j(self, neo4j_http_port=7474, neo4j_bolt_port=7687, neo4j_auth="none"):
        logging.debug("Running container")
        container_full_name = f"{self.name}-{self.instant}"
        subprocess.run([
            "docker",
            "run",
            "-d", "--name", container_full_name,
            "-p", f"{neo4j_http_port}:7474", "-p", f"{neo4j_bolt_port}:7687",
            "-e", f"NEO4J_AUTH={neo4j_auth}",
            "-v", f"{container_full_name}:/data",
            f"{self.name}:{self.instant}"
        ], capture_output=True)
        self.dirty["container"].append(container_full_name)

    def clean(self):
        if "container" in self.dirty:
            logging.debug("Closing and removing containers")
            for container in self.dirty["container"]:
                subprocess.run(["docker", "stop", container], capture_output=True)
                subprocess.run(["docker", "rm", container], capture_output=True)
        if "image" in self.dirty:
            logging.debug("Removing images")
            for image in self.dirty["image"]:
                subprocess.run(["docker", "rmi", image], capture_output=True)
        if "volume" in self.dirty:
            logging.debug("Removing volumes")
            for volume in self.dirty["volume"]:
                subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


def rename_volume(old_volume, new_volume):
    client = docker.from_env()

    volumes = client.volumes.list()
    assert any(v.name == old_volume for v in volumes), f"Volume not found: {old_volume}"
    assert not any(v.name == new_volume for v in volumes), f"Volume already exists: {new_volume}"

    client.volumes.create(name=new_volume)
    client.containers.run(
        "alpine",
        command="sh -c 'cp -av /old/. /new/'",
        volumes={
            old_volume: {"bind": "/old", "mode": "ro"},
            new_volume: {"bind": "/new", "mode": "rw"}
        },
        remove=True
    )


def get_container_volumes(container_name):
    """Get named volumes attached to a container."""
    result = subprocess.run(
        ["docker", "inspect", container_name, "--format", "{{json .Mounts}}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    mounts = json.loads(result.stdout)
    return [m["Name"] for m in mounts if m.get("Type") == "volume"]


def container_exists(container_name):
    result = subprocess.run(
        ["docker", "container", "inspect", container_name],
        capture_output=True,
    )
    return result.returncode == 0


def container_running(container_name):
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def network_exists(network_name):
    result = subprocess.run(
        ["docker", "network", "inspect", network_name],
        capture_output=True,
    )
    return result.returncode == 0
