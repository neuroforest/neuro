import contextlib
import os
import subprocess

from neuro.utils import terminal_components


def quiet():
    """Return True unless VERBOSE is set."""
    return not os.environ.get("VERBOSE")


PARTS = ("major", "minor", "patch")


def bump_version(current, part):
    """Return current semver string with part (major, minor, patch) incremented."""
    if part not in PARTS:
        raise ValueError(f"Unknown version part: {part}. Choose from {', '.join(PARTS)}")
    numbers = current.split(".")
    if len(numbers) != 3 or not all(n.isdigit() for n in numbers):
        raise ValueError(f"Not a semantic version: {current}")
    index = PARTS.index(part)
    numbers = [int(n) for n in numbers]
    numbers[index] += 1
    numbers[index + 1:] = [0] * (2 - index)
    return ".".join(str(n) for n in numbers)


def rsync_local(source, dest, name=None):
    """Rsync submodule into app/ with gitignore filter."""
    rsync_command = [
        "rsync", "-va",
        "--filter=P .git",
        "--filter=:- .gitignore",
        "--delete", "--delete-excluded",
        source, dest,
    ]
    if not name:
        name = os.path.basename(source)
    with terminal_components.step(f"Sync {name}"):
        subprocess.run(rsync_command, check=True, capture_output=True)


@contextlib.contextmanager
def chdir(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)
