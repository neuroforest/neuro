"""
Moves a file or directory both locally and in NeuroWiki.
"""

import os

import click

from neuro.core.deep import Dir
from neuro.tools.terminal import common
from neuro.tools.terminal.cli import pass_environment
from neuro.utils import SETTINGS


def move_file(src_path, dst_path):
    src_dir = Dir(src_path)

    # Handle symlinks
    for search_dir in SETTINGS.LOCAL_INCLUDE:
        symlinks = os.popen(f"find {search_dir} -type l").read()[:-1].split("\n")
        for symlink in symlinks:
            symlink_target = os.readlink(symlink)
            if src_path in symlink_target:
                new_symlink_target = symlink_target.replace(src_path, dst_path)
                os.system(f"rm {symlink}")
                os.system(f"ln -s {new_symlink_target} {symlink}")

    src_dir.move(dst_path)


@click.command("mv", short_help="move file")
@click.argument("src_path", type=click.Path(dir_okay=True, exists=True, resolve_path=True, writable=True))
@click.argument("dst_path", type=click.Path(dir_okay=True, resolve_path=True, writable=True))
@pass_environment
def cli(ctx, src_path, dst_path):
    """
    :param ctx:
    :param src_path: current file pathname
    :param dst_path: target file pathname
    """
    if not os.path.exists(src_path):
        print(f"Error: not found {src_path}")
        return
    if os.path.exists(dst_path):
        print(f"Error: already exists {dst_path}")
        return

    # Replace text in NeuroWiki
    res = common.replace_text(src_path, dst_path, "")

    # Move file locally
    if res:
        move_file(src_path, dst_path)
