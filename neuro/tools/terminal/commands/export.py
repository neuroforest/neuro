"""
Custom export of a tiddler.
"""

import re

import click

from neuro.core.files.text import TextCsv
from neuro.tools.api import tw_get
from neuro.tools.terminal.cli import pass_environment


def parse_table(tid_text):
    rows = tid_text.split("\n")
    lol = list()
    for row in rows:

        # Ignore special rows
        if not row:
            continue
        if row[-1].isalpha():
            continue

        # Extract header
        row = "".join(row.split("`"))
        if row[:2] == "|!":
            pattern = r"(?=(\|\!(.*?)\|))"
            matches = [match.group(2) for match in re.finditer(pattern, row)]
            lol.append(matches)
            continue

        # Extract row
        matches = list()
        count = 0
        temp = ""
        ignore = False
        row = row[1:-1]
        for c in row:
            if c == "|" and count == 0:
                matches.append(temp)
                temp = ""
                continue
            if c == "|" and count == 2:
                ignore = True
                continue
            if c == "[":
                count += 1
                continue
            if c == "]":
                count -= 1
                if count == 0:
                    ignore = False
                continue
            if not ignore:
                temp = temp + c

        if temp:
            matches.append(temp)
        lol.append(matches)

    return lol


@click.command("export", short_help="export a tiddler")
@click.option("--mode", cls=click.Option, type=str)
@click.argument("title", required=True)
@click.argument("path", type=click.Path(exists=False, resolve_path=True, writable=True))
@pass_environment
def cli(ctx, title, mode, path):
    tid_text = tw_get.tiddler(title)["text"]
    if mode == "table":
        lol = parse_table(tid_text)
        TextCsv(path=path, mode="w+").write(lol)
    else:
        print(f"Mode '{mode}' is not supported")
