"""
Move a file or directory both locally and in NeuroWiki.
"""

import os
import subprocess

import click

from neuro.core.deep import Dir
from neuro.tools.terminal import common, style
from neuro.tools.terminal.cli import pass_environment


def move_file(src_path, dst_path):
    src_dir = Dir(src_path)

    # Handle symlinks
    symlink_count = 0
    local_include = os.getenv("LOCAL_INCLUDE").split(",") if os.getenv("LOCAL_INCLUDE") else []
    for search_dir in local_include:
        p = subprocess.run(["find", search_dir, "-type", "l"], stdout=subprocess.PIPE)
        symlinks = p.stdout.decode(encoding="utf-8").split("\n")
        symlinks = list(filter(None, symlinks))
        for symlink in symlinks:
            symlink_target = os.readlink(symlink)
            if src_path in symlink_target:
                symlink_count +=1
                new_symlink_target = symlink_target.replace(src_path, dst_path)
                os.system(f"rm {symlink}")
                os.system(f"ln -s {new_symlink_target} {symlink}")

    if symlink_count == 0:
        print(f"{style.FAIL} 0 symlinks affected")
    else:
        print(f"{style.SUCCESS} {symlink_count} symlinks affected")

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
