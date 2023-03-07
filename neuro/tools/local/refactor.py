"""
Refactor local directories and update the wiki accordingly.
"""
import json
import logging
import os
import shlex
import subprocess

from neuro.core.deep import Dir, File
from neuro.utils import internal_utils
from neuro.tools.terminal import style

logging.basicConfig(level=logging.INFO)


def update_tiddlers(old, new, tiddlers_path):
    """
    Update text in tiddlers by editing local files.
    :param old:
    :param new:
    :param tiddlers_path:
    """
    # Perform full-text search
    old_safe_quoted = shlex.quote(old)
    old_safe_quoted = old_safe_quoted.replace("[", "\\[")
    old_safe_quoted = old_safe_quoted.replace("]", "\\]")
    old_safe_quoted = old_safe_quoted.replace("|", "\\|")
    command = f"grep -rn {tiddlers_path} -e {old_safe_quoted}"
    fts_result = os.popen(command).read()
    fts_lines = fts_result.split("\n")[:-1]
    # Perform full-text replace in affected files
    for fts_line in fts_lines:
        tiddler_path = tuple(fts_line.split(":", 1))[0]
        with open(tiddler_path) as f:
            text = f.read()
        new_text = text.replace(old, new)
        with open(tiddler_path, "w") as f:
            f.write(new_text)

    print(f"{style.SUCCESS} {len(fts_lines)} tiddlers affected")


def transform(html_wiki, wiki_folder, tw5="tw5/tiddlywiki.js"):
    """
    Convert HTML wiki to wikifolder.
    :param html_wiki:
    :param wiki_folder: path to established wikifolder with tiddlywiki.info file
    :param tw5:
    :return:
    """
    p = subprocess.Popen([
        "node",
        tw5,
        wiki_folder,
        "--load",
        html_wiki
        ], stdout=subprocess.DEVNULL)
    p.wait()
    p.kill()
