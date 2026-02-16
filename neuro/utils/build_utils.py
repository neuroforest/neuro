import contextlib
import os
import subprocess

from neuro.utils import internal_utils, terminal_style


def rsync_local(source, dest, name=None):
    """Rsync submodule into app/ with gitignore filter."""
    rsync_command = [
        "rsync", "-va",
        "--filter=:- .gitignore",
        "--exclude=.git",
        "--delete",
        source, dest,
    ]
    if not name:
        name = os.path.basename(source)
    with terminal_style.step(f"Sync {name}"):
        subprocess.run(rsync_command, check=True, capture_output=True)


@contextlib.contextmanager
def chdir(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)
