"""
Full-text search
"""

import re

import click

from neuro.base.api import nb_get
from neuro.core.data.dict import DictUtils
from neuro.tools.terminal.cli import pass_environment
from neuro.utils import terminal_style


@click.command("fts", short_help="full-text search")
@click.argument("query", required=True)
@pass_environment
def cli(ctx, query):
    fields_list = nb_get.all_fields()
    matches = dict()
    for fields in fields_list:
        title = fields["title"]
        for key, value in fields.items():
            if query in str(value):
                if title not in matches:
                    matches[title] = dict()
                matches[title][key] = value

    styled_matches = dict()
    for key, value in matches.items():
        key = terminal_style.BOLD + key + terminal_style.RESET
        styled_matches[key] = dict()
        for k, v in value.items():
            v = str(v).replace("\n", " ")
            if k == "text":
                styled_matches[key]["text"] = list()
                for match in re.finditer(query, v):
                    if match.start() < 10:
                        start = 0
                    else:
                        start = match.start() - 10
                    if match.end() > len(v) - 10:
                        end = len(v)
                    else:
                        end = match.end() + 10
                    styled_matches[key]["text"].append(str(
                        v[start:match.start()]
                        + terminal_style.RED
                        + v[match.start():match.end()]
                        + terminal_style.RESET
                        + v[match.end():end]))
            else:
                styled_matches[key][k] = v.replace(query, str(
                    terminal_style.RED
                    + query
                    + terminal_style.RESET))

    if styled_matches:
        DictUtils.represent(styled_matches)
    else:
        print("No matches found")
