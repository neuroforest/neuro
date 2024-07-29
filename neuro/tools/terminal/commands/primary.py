"""
Analyse and autofill fields neuro.primary.
"""

import click
import pyperclip

from neuro.core.data.dict import DictUtils
from neuro.tools.api import tw_get, tw_put
from neuro.tools.terminal import style
from neuro.tools.terminal.cli import pass_environment


def resolve_simple_error(tw_fields):
    for tf in tw_fields:
        title = tf["title"]
        neuro_tid = tw_get.neuro_tid(title)
        neuro_tid.fields["neuro.primary"] = tf["tags"][0]
        print(f"Resolved simple error: {title}")
        tw_put.neuro_tid(neuro_tid)


def resolve_simple_no_primary(tw_fields):
    for tf in tw_fields:
        title = tf["title"]
        neuro_tid = tw_get.neuro_tid(title)
        neuro_tid.fields["neuro.primary"] = tf["tags"][0]
        print(f"Added primary: {title}")
        tw_put.neuro_tid(neuro_tid)


def resolve_simple_no_tags(tw_fields):
    no_tags = [tf for tf in tw_fields if "#" not in tf["title"]]
    if not no_tags:
        return
    print(f"\n{style.YELLOW}{style.BOLD}NOTE:{style.RESET} {len(no_tags)} tiddlers have no tags")
    for tf in no_tags:
        print(f"- {tf['title']}")


def resolve_complex_error(tw_fields):
    for tf in tw_fields:
        print(f"\n{'-'*30}\nSetting primary for {style.BOLD}{tf['title']}{style.RESET}", end="")
        if "neuro.primary" in tf:
            print(f" (current {tf['neuro.primary']})")
        else:
            print()
        tag_indices = range(len(tf["tags"]))
        tid_title = tf["title"]
        for i in tag_indices:
            print(f"{i + 1} - {tf['tags'][i]}")

        pyperclip.copy(tid_title)
        temp = input(f"Select {' | '.join([str(i + 1) for i in tag_indices])},"
                     f" input 'n' to cancel or write valid tiddler name\n")
        tiddler_chosen = str()
        if temp == "n" or not temp:
            continue
        elif temp.isnumeric():
            if int(temp) - 1 in tag_indices:
                tiddler_chosen = tf["tags"][int(temp) - 1]
            else:
                print(f"{style.RED}Numeric, but invalid{style.RESET}")
                continue
        else:
            if tw_get.is_tiddler(temp):
                tiddler_chosen = temp
            else:
                print(f"Tiddler '{temp}' not found")

        if tiddler_chosen:
            neuro_tid = tw_get.neuro_tid(tid_title)
            neuro_tid.fields["neuro.primary"] = tiddler_chosen
            if tiddler_chosen not in neuro_tid.fields["tags"]:
                neuro_tid.fields["tags"].append(tiddler_chosen)
                print(f"Added tag and primary {tiddler_chosen}")
            tw_put.neuro_tid(neuro_tid)


def analyse():
    tw_fields = tw_get.tw_fields(["title", "neuro.primary", "tags"], "[!is[system]]", )

    sorting_bin = {
        "primary=tag": list(),
        "primary≠tag": list(),
        "primary∈tags": list(),
        "primary∉tags": list(),
        "¬∃primary∃tag": list(),
        "¬∃primary∃tags": list(),
        "¬∃primary¬∃tag": list(),
        "∃primary¬∃tag": list()
    }

    for tf in tw_fields:
        tags = list()
        if "tags" in tf:  # Short-circuiting
            tags = tf["tags"]

        if not tags:
            if "neuro.primary" in tf:
                sorting_bin["∃primary¬∃tag"].append(tf)
            else:
                sorting_bin["¬∃primary¬∃tag"].append(tf)
            continue

        if "neuro.primary" not in tf:
            if len(tags) == 1:
                sorting_bin["¬∃primary∃tag"].append(tf)
            else:
                sorting_bin["¬∃primary∃tags"].append(tf)
        else:
            np = tf["neuro.primary"]
            if np in tags:
                if len(tags) == 1:
                    sorting_bin["primary=tag"].append(tf)
                else:
                    sorting_bin["primary∈tags"].append(tf)
            else:
                if len(tags) == 1:
                    sorting_bin["primary≠tag"].append(tf)
                else:
                    sorting_bin["primary∉tags"].append(tf)

    counter = dict()
    for key in sorting_bin:
        counter[key] = len(sorting_bin[key])   

    print("")
    print("-"*30)
    DictUtils.represent(counter)

    return sorting_bin


@click.command("primary", short_help="analyse neuro.primary")
@pass_environment
def cli(ctx):
    sorting_bin = analyse()
    resolve_simple_error(sorting_bin["primary≠tag"])
    resolve_simple_no_primary(sorting_bin["¬∃primary∃tag"])
    resolve_simple_no_tags(sorting_bin["¬∃primary¬∃tag"])
    resolve_complex_error(sorting_bin["primary∉tags"])
    resolve_complex_error(sorting_bin["¬∃primary∃tags"])
