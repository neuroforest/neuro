"""
Quality assurance.

Before a wiki is archived, certain criteria must be satisfied.
"""

import os
import json

import click
import pyperclip
from rich.console import Console
import tqdm

from neuro.core.tid import NeuroTids
from neuro.tools.tw5api import tw_actions, tw_del, tw_get, tw_put
from neuro.tools.terminal import style, components
from neuro.tools.terminal.cli import pass_environment


def remove_ghost_tiddlers(port):
    tid_titles = tw_get.tid_titles("[search:title[Draft of ']!has[draft.of]]", port=port)
    for tid_title in tid_titles:
        tw_del.tiddler(tid_title, port=port)
        print(f"Removed {tid_title}")


def resolve_neuro_ids(port, verbose=False):
    resolved = True

    # Add neuro.id
    unidentified = tw_get.neuro_tids("[!is[system]!has[neuro.id]]", port=port)
    if unidentified:
        print("Adding neuro.id fields:")
        width = max([len(neuro_tid.title) for neuro_tid in unidentified])
        with tqdm.tqdm(total=len(unidentified)) as pbar:
            for neuro_tid in unidentified:
                pbar.set_description(neuro_tid.title.ljust(width))
                tw_put.neuro_tid(neuro_tid, port=port)
                pbar.update(1)
            pbar.set_description("")

    # Find potential neuro.id duplicates
    all_nids = tw_get.filter_output("[has[neuro.id]get[neuro.id]]", port=port)
    seen = set()
    duplicates = set()
    for nid in all_nids:
        if nid in seen:
            duplicates.add(nid)
        else:
            seen.add(nid)

    if duplicates:
        resolved = False
        if verbose:
            print("The following neuro.id conflicts ware found")
            duplicates = list(duplicates)
            for i in range(len(duplicates)):
                nid = duplicates[i]
                tid_titles = tw_get.filter_output(f"[search:neuro.id:literal[{nid}]]", port=port)
                print(f"{i+1}) {nid}:\n\t{'\n\t'.join(tid_titles)}")

    if not all([len(nid) == 36 for nid in seen]):
        resolved = False
        print("neuro.id length variability detected")

    if resolved:
        print(f"{style.SUCCESS} Neuro ID")
    else:
        print(f"{style.FAIL} Neuro ID")

    return resolved


def set_journal(port):
    update_tids = tw_get.neuro_tids("[tag[JOURNAL]!has[neuro.role]]", port=port)
    if update_tids:
        print(f"\nJournal roles: {len(update_tids)}")
        width = max([len(neuro_tid.title) for neuro_tid in update_tids])
        with tqdm.tqdm(total=len(update_tids)) as pbar:
            for neuro_tid in update_tids:
                pbar.set_description(neuro_tid.title.ljust(width))
                neuro_tid.add_fields({"neuro.role": "journal"})
                tw_put.neuro_tid(neuro_tid, port=port)
                pbar.update(1)
            pbar.set_description("")

    print(f"{style.SUCCESS} Journal")


def set_roles(port):
    role_pairs = dict()
    for tid_tag, role in json.loads(os.getenv("ROLE_DICT")).items():
        neuro_tids = tw_get.neuro_tids(f"[tag[{tid_tag}]!has[neuro.role]]", port=port)
        for neuro_tid in neuro_tids:
            role_pairs[neuro_tid.title] = role

    if role_pairs:
        print(f"\nSetting roles for {len(role_pairs)} tiddlers")
        width = max([len(tid_title) for tid_title in role_pairs])
        with tqdm.tqdm(total=len(role_pairs)) as pbar:
            for tid_title, role in role_pairs.items():
                pbar.set_description(tid_title.ljust(width))
                neuro_tid = tw_get.neuro_tid(tid_title, port=port)
                neuro_tid.add_fields({"neuro.role": role})
                tw_put.neuro_tid(neuro_tid, port=port)
                pbar.update(1)
            pbar.set_description("")

    print(f"{style.SUCCESS} Roles set")


def set_model_roles(port):
    update_tids = NeuroTids()
    for model_role in json.loads(os.getenv("MODEL_ROLES")):
        regexp_pattern = r"^\S+\s\S+$"
        model_tids = tw_get.neuro_tids(f"[prefix[.]suffix[ {model_role}]!has[neuro.role]"
                                       f"regexp[{regexp_pattern}]]", port=port)
        update_tids.extend(model_tids)

    if update_tids:
        print(f"\nModel roles: {len(update_tids)}")
        width = max([len(neuro_tid.title) for neuro_tid in update_tids])
        with tqdm.tqdm(total=len(update_tids)) as pbar:
            for neuro_tid in update_tids:
                pbar.set_description(neuro_tid.title.ljust(width))
                pbar.update(1)
                neuro_tid.add_fields({"neuro.role": "model"})
                tw_put.neuro_tid(neuro_tid, port=port)
            pbar.set_description("")
    print(f"{style.SUCCESS} Model roles")


def validate_tags(port, interactive=False, verbose=True):
    """
    Validate every non-system tiddler to have a tag that is itself a tiddler.
    :param port:
    :param interactive:
    :param verbose:
    :return:
    """
    validated = True
    tfs = tw_get.tw_fields(["title", "tags"], "[!is[system]]", port=port)
    transformed_index = dict()
    for tf in tfs:
        tid_title = tf["title"]
        transformed_index[tid_title] = tf

    no_tags = list()
    for tid_title, tf in transformed_index.items():
        invalid_tags = list()
        if "tags" not in tf or not tf["tags"]:
            if " #" in tid_title or "Draft of " in tid_title:
                pass
            else:
                no_tags.append(tid_title)
            continue

        for tag in tf["tags"]:
            if tag.startswith("$:/"):
                continue
            elif tag not in transformed_index:
                invalid_tags.append(tag)

        if invalid_tags:
            validated = False
            if interactive:
                print(f"{style.YELLOW}{style.BOLD}{tid_title}{style.RESET} has invalid tags:")
                tw_actions.open_tiddler(tid_title)
                for tag in invalid_tags:
                    print(f"    - {tag}")
                input()
            else:
                print(f"{style.YELLOW}{style.BOLD}{tid_title}{style.RESET} has invalid tags {' | '.join(invalid_tags)}")

    # Resolve no tag tiddlers
    if no_tags:
        validated = False
        if interactive:
            for tid_title in no_tags:
                print(f"{style.YELLOW}{style.BOLD}{no_tags[0]}{style.RESET} has no tags")
                tw_actions.open_tiddler(tid_title)
                input()
        else:
            no_tags_len = len(no_tags)
            if no_tags_len == 1:
                print(f"{style.YELLOW}{style.BOLD}{no_tags[0]}{style.RESET} has no tags")
            else:
                print(f"{style.YELLOW}{style.BOLD}NOTE:{style.RESET} {no_tags_len} "
                      f"tiddlers have no tags")
                for tid_title in no_tags:
                    print(f"    - {tid_title}")

    if verbose:
        if validated:
            print(f"{style.SUCCESS} Tags resolved")
        else:
            print(f"{style.FAIL} Invalid tags")

    return validated


def resolve_missing_tiddlers(port, interactive=False, verbose=True):
    validated = True
    missing_tiddlers = tw_get.filter_output("[all[missing]!is[system]]", port=port)
    if missing_tiddlers:
        validated = False
    for missing_tiddler in missing_tiddlers:
        backlinks = tw_get.filter_output(f"[[{missing_tiddler}]backlinks[]]", port=port)
        for backlink in backlinks:
            if interactive:
                print(f"{style.YELLOW}{style.BOLD}{backlink}{style.RESET} has a broken link")
                tw_actions.open_tiddler(backlink)
                input()
            else:
                print(f"{style.YELLOW}{style.BOLD}{backlink}{style.RESET} has a broken link")

    if verbose:
        if validated:
            print(f"{style.SUCCESS} Missing tiddlers resolved")
        else:
            print(f"{style.FAIL} Missing tiddlers")

    return validated


class Primary:
    def __init__(self, interactive, port, verbose):
        self.validated = True
        self.port = port
        self.verbose = verbose
        self.interactive = interactive
        self.sorting_bin = {
            "primary=tag": list(),
            "primary≠tag": list(),
            "primary∈tags": list(),
            "primary∉tags": list(),
            "¬∃primary∃tag": list(),
            "¬∃primary∃tags": list(),
            "¬∃primary¬∃tag": list(),
            "∃primary¬∃tag": list()
        }
        self.simple_tfs = list()
        self.complex_tfs = list()
        self.lineage_integrity = True

    def analyse(self):
        tw_fields = tw_get.tw_fields(["title", "neuro.primary", "tags"], "[!is[system]]", port=self.port)
        for tf in tw_fields:
            tags = list()
            if "tags" in tf:  # Short-circuiting
                tags = tf["tags"]

            if not tags:
                if "neuro.primary" in tf:
                    self.sorting_bin["∃primary¬∃tag"].append(tf)
                else:
                    self.sorting_bin["¬∃primary¬∃tag"].append(tf)
                continue

            if "neuro.primary" not in tf:
                if len(tags) == 1:
                    self.sorting_bin["¬∃primary∃tag"].append(tf)
                else:
                    self.sorting_bin["¬∃primary∃tags"].append(tf)
            else:
                np = tf["neuro.primary"]
                if np in tags:
                    if len(tags) == 1:
                        self.sorting_bin["primary=tag"].append(tf)
                    else:
                        self.sorting_bin["primary∈tags"].append(tf)
                else:
                    if len(tags) == 1:
                        self.sorting_bin["primary≠tag"].append(tf)
                    else:
                        self.sorting_bin["primary∉tags"].append(tf)

        if self.verbose:
            counter = dict()
            for key in sorting_bin:
                counter[key] = len(sorting_bin[key])

            print("")
            print("-" * 30)
            DictUtils.represent(counter)

    def verify_lineage(self):
        lineage_root = "$:/plugins/neuroforest/front/tags/Contents"
        lineage = tw_get.lineage(lineage_root, port=self.port)
        cycles = list()
        for tid_title, lineage_item in lineage.items():
            if not lineage_item:
                pass
            elif len(lineage_item) >= 20:
                cycle = list()
                for tt in lineage_item:
                    if tt not in cycle:
                        cycle.append(tt)
                if set(cycle) not in [set(c) for c in cycles]:
                    cycles.append(cycle)
                self.lineage_integrity = False
            elif lineage_item[0] != lineage_root:
                if lineage_item[0].startswith("$:/"):
                    # These are system rooted tiddlers
                    pass
                else:
                    self.lineage_integrity = False
                    print(
                        f"Lineage problem for tiddler {style.YELLOW}{style.BOLD}{tid_title}{style.RESET}:")
                    print(" - ".join(lineage_item))
            else:
                pass

        # Resolve cycles
        if cycles:
            print("Cycles found:")
            for cycle in cycles:
                print("    " + " - ".join(cycle))

    def resolve_simple(self):
        simple_tfs = self.sorting_bin["primary≠tag"] + self.sorting_bin["¬∃primary∃tag"]
        if len(simple_tfs) > 0:
            print(f"\nAutomated corrections: {len(simple_tfs)}")
        else:
            return

        width = min([max([len(tf["title"]) for tf in simple_tfs]), 24])
        with tqdm.tqdm(total=len(simple_tfs)) as pbar:
            for tf in simple_tfs:
                title = tf["title"]
                neuro_tid = tw_get.neuro_tid(title, port=self.port)
                neuro_tid.fields["neuro.primary"] = tf["tags"][0]
                if self.verbose:
                    if "primary" in tf:
                        print(f"Resolved simple error: {title}")
                    else:
                        print(f"Added primary: {title}")
                else:
                    pbar.set_description(title.ljust(width)[:width])
                    pbar.update(1)
                tw_put.neuro_tid(neuro_tid, port=self.port)
            pbar.set_description("")

    def resolve_complex(self):
        complex_tfs = self.sorting_bin["primary∉tags"] + self.sorting_bin["¬∃primary∃tags"]
        if complex_tfs and not self.interactive:
            self.validated = False
            return

        for tf in complex_tfs:
            tid_title = tf["title"]
            tid_tags = sorted(tf['tags'])
            tw_actions.open_tiddler(tid_title)
            print(f"\n{'-' * 30}\nSetting primary for {style.BOLD}{tf['title']}{style.RESET}", end="")
            if "neuro.primary" in tf:
                print(f" (current {tf['neuro.primary']})")
            else:
                print()
            pyperclip.copy(tid_title)
            tiddler_chosen = components.selector(tid_tags)

            if tiddler_chosen:
                neuro_tid = tw_get.neuro_tid(tid_title, port=self.port)
                neuro_tid.fields["neuro.primary"] = tiddler_chosen
                tw_put.neuro_tid(neuro_tid, port=self.port)
            else:
                self.validated = False

    def report(self):
        self.analyse()
        if self.sorting_bin["∃primary¬∃tag"]:
            self.validated = False
            print(f"Rare error: {self.sorting_bin['∃primary¬∃tag']}")
        if self.simple_tfs:
            self.validated = False
            raise exceptions.InternalError("Automated corrections")
        if self.complex_tfs:
            self.validated = False
            print(f"{style.FAIL} Manual corrections were not resolved")
        if not self.lineage_integrity:
            self.validated = False
            print(f"{style.FAIL} Lineage problems")

        if self.validated:
            print(f"{style.SUCCESS} Primary resolved")

    def run(self):
        self.analyse()
        self.resolve_simple()
        self.resolve_complex()
        self.report()
        return self.validated


@click.command("qa", short_help="quality assurance")
@click.option("-i", "--interactive", is_flag=True)
@click.option("--port", default=os.getenv("PORT"))
@click.option("-v", "--verbose", is_flag=True)
@pass_environment
def cli(ctx, interactive, port, verbose):
    """
    :param ctx:
    :param interactive:
    :param port:
    :param verbose:
    """

    remove_ghost_tiddlers(port)
    set_model_roles(port)
    set_roles(port)
    set_journal(port)

    if interactive:
        with Console().status("Validating tags...", spinner="dots"):
            validate_tags(port, interactive=True, verbose=False)
            resolve_missing_tiddlers(port, interactive=True, verbose=False)

    tags_response = validate_tags(port)
    missing_response = resolve_missing_tiddlers(port)
    primary_response = Primary(interactive, port, verbose).run()
    neuro_ids_response = resolve_neuro_ids(port, verbose=True)

    return all([tags_response, missing_response, primary_response, neuro_ids_response])
