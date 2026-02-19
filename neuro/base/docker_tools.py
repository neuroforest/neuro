"""
Tools for Docker container management.
"""

import json
import logging
import os
import subprocess

import docker

from neuro.core import Dir
from neuro.utils import internal_utils, time_utils


class Container:
    def __init__(self, name=None, archive=None):
        self.name = name
        self.instant = str()
        self.archive = archive or internal_utils.get_path("archive", create_if_missing=True) + "/base"
        os.makedirs(self.archive, exist_ok=True)
        self.backup_location = str()
        self.dirty = {
            "container": list(),
            "image": list(),
            "volume": list()
        }

    @staticmethod
    def is_valid_backup(b):
        if os.path.isfile(f"{b}/data.tar.gz") and os.path.isfile(f"{b}/container.tar"):
            return True
        else:
            return False

    def backup(self):
        """
        Backup docker container and associated data.
        """
        if not self.name:
            raise ValueError("Container name not provided.")
        self.instant = time_utils.MOMENT_4
        self.backup_location = f"{self.archive}/{self.name}-{self.instant}"
        os.makedirs(self.backup_location)
        self.backup_data()
        self.backup_container()

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
        # Find /data mount
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
        data_mount = dict()
        for mount in mounts:
            if mount["Destination"] == "/data":
                data_mount = mount
                break
        data_mount_id = data_mount["Name"]
        logging.debug(f"Found /data volume: {data_mount_id}")

        # Copy /data volume to an independent volume
        data_backup_volume_name = f"{self.name}-{self.instant}"
        subprocess.run([
            "docker",
            "run", "--rm",
            "-v", f"{data_mount_id}:/from",
            "-v", f"{data_backup_volume_name}:/to",
            "alpine", "ash", "-c",
            "cd /from && cp -a . /to"
        ], capture_output=True)
        logging.debug(f"Copied /data volume to {data_backup_volume_name}")
        self.dirty["volume"].append(data_backup_volume_name)

        # Verify
        result = subprocess.run([
            "docker",
            "volume",
            "ls"], capture_output=True, text=True)
        if data_backup_volume_name not in result.stdout:
            raise Exception(f"Backup error: volume {data_mount_id} not found.")

        # Export volume to tar.gz file
        subprocess.run([
            "docker",
            "run", "--rm",
            "-v", f"{data_backup_volume_name}:/data",
            "-v", f"{self.backup_location}:/backup",
            "alpine", "sh", "-c",
            "cd /data && tar czf /backup/data.tar.gz ."
        ], capture_output=True)
        logging.debug(f"Archived /data to {self.backup_location}/data.tar.gz")

    def backup_container(self):
        backup_name = f"{self.name}:{self.instant}"
        subprocess.run([
            "docker",
            "commit",
            self.name,
            backup_name
        ], capture_output=True)
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

        # Archive container
        subprocess.run([
            "docker",
            "save",
            backup_name,
            "-o", f"{self.backup_location}/container.tar"
        ], capture_output=True)

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
        self.restore_container()

    def restore_data(self):
        logging.debug("Restoring data")
        volume_name = f"{self.name}-{self.instant}"
        subprocess.run([
            "docker",
            "run", "--rm",
            "-v",  f"{volume_name}:/data",
            "-v", f"{self.backup_location}:/backup",
            "alpine", "sh", "-c",
            "cd /data && tar xzf /backup/data.tar.gz"
        ], capture_output=True)
        self.dirty["volume"].append(volume_name)

    def restore_container(self):
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
