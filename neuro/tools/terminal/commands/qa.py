"""
Quality assurance.

Before a wiki is archived, certain criteria must be satisfied.
"""

import os
import json
from abc import ABC, abstractmethod

import click
import pyperclip
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn

from neuro.core.tid import TiddlerList
from neuro.core.data.dict import DictUtils
from neuro.tools.tw5api import tw_actions, tw_del, tw_get, tw_put
from neuro.tools.terminal.cli import pass_environment
from neuro.utils import exceptions, network_utils, terminal_components, terminal_style


def _truncate(text, max_len=32):
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


def _progress():
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    )


class QACheck(ABC):
    name: str

    def __init__(self, port):
        self.port = port

    @abstractmethod
    def run(self) -> bool: ...


class GhostTiddlers(QACheck):
    name = "Ghost Tiddlers"

    def run(self) -> bool:
        tid_titles = tw_get.tid_titles("[search:title[Draft of ']!has[draft.of]]", port=self.port)
        for tid_title in tid_titles:
            tw_del.tiddler(tid_title, port=self.port)
            print(f"Removed {tid_title}")
        return True


class ObjectSets(QACheck):
    name = "Object Sets"

    def run(self) -> bool:
        update_list = TiddlerList()
        object_sets_raw = os.getenv("OBJECT_SETS")
        if not object_sets_raw:
            print(f"{terminal_style.FAIL} OBJECT_SETS environment variable is not set")
            return False
        for object_set in json.loads(object_sets_raw):
            regexp_pattern = r"^\S+\s\S+$"
            tiddler_list = tw_get.tiddler_list(
                f"[prefix[.]suffix[ {object_set}]!has[neuro.role]regexp[{regexp_pattern}]]",
                port=self.port,
            )
            update_list.extend(tiddler_list)

        if update_list:
            with _progress() as progress:
                task = progress.add_task("Object sets", total=len(update_list))
                for tiddler in update_list:
                    progress.update(task, description=f"Object sets: {_truncate(tiddler.title).ljust(32)}")
                    tiddler.add_fields({"neuro.role": "model"})
                    tw_put.tiddler(tiddler, port=self.port)
                    progress.advance(task)
                progress.update(task, description="Object sets".ljust(32))

        print(f"{terminal_style.SUCCESS} Object sets")
        return True


class Roles(QACheck):
    name = "Roles"

    def run(self) -> bool:
        role_pairs = dict()
        role_dict_raw = os.getenv("ROLE_DICT")
        if not role_dict_raw:
            print(f"{terminal_style.FAIL} ROLE_DICT environment variable is not set")
            return False
        for tid_tag, role in json.loads(role_dict_raw).items():
            tiddler_list = tw_get.tiddler_list(f"[tag[{tid_tag}]!has[neuro.role]]", port=self.port)
            for tiddler in tiddler_list:
                role_pairs[tiddler.title] = role

        if role_pairs:
            with _progress() as progress:
                task = progress.add_task("Roles", total=len(role_pairs))
                for tid_title, role in role_pairs.items():
                    progress.update(task, description=f"Roles: {_truncate(tid_title).ljust(32)}")
                    tiddler = tw_get.tiddler(tid_title, port=self.port)
                    tiddler.add_fields({"neuro.role": role})
                    tw_put.tiddler(tiddler, port=self.port)
                    progress.advance(task)
                progress.update(task, description="Roles".ljust(32))

        print(f"{terminal_style.SUCCESS} Roles")
        return True


class ValidateTags(QACheck):
    name = "Tags"

    def __init__(self, port, interactive=False):
        super().__init__(port)
        self.interactive = interactive

    def run(self) -> bool:
        validated = True
        tfs = tw_get.tw_fields(["title", "tags"], "[!is[system]]", port=self.port)
        transformed_index = {tf["title"]: tf for tf in tfs}

        no_tags = []
        for tid_title, tf in transformed_index.items():
            invalid_tags = []
            if "tags" not in tf or not tf["tags"]:
                if " #" not in tid_title and "Draft of " not in tid_title:
                    no_tags.append(tid_title)
                continue

            for tag in tf["tags"]:
                if tag.startswith("$:/"):
                    continue
                elif tag not in transformed_index:
                    invalid_tags.append(tag)

            if invalid_tags:
                validated = False
                if self.interactive:
                    print(f"{terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET} has invalid tags:")
                    tw_actions.open_tiddler(tid_title)
                    for tag in invalid_tags:
                        print(f"    - {tag}")
                    input()
                else:
                    print(f"{terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET} has invalid tags {' | '.join(invalid_tags)}")

        if no_tags:
            validated = False
            if self.interactive:
                for tid_title in no_tags:
                    print(f"{terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET} has no tags")
                    tw_actions.open_tiddler(tid_title)
                input()
            else:
                no_tags_len = len(no_tags)
                if no_tags_len == 1:
                    print(f"{terminal_style.YELLOW}{terminal_style.BOLD}{no_tags[0]}{terminal_style.RESET} has no tags")
                else:
                    print(f"{terminal_style.YELLOW}{terminal_style.BOLD}NOTE:{terminal_style.RESET} {no_tags_len} tiddlers have no tags")
                    for tid_title in no_tags:
                        print(f"    - {tid_title}")

        if validated:
            print(f"{terminal_style.SUCCESS} Tags")
        else:
            print(f"{terminal_style.FAIL} Invalid tags")

        return validated


class MissingTiddlers(QACheck):
    name = "Missing Tiddlers"

    def __init__(self, port, interactive=False):
        super().__init__(port)
        self.interactive = interactive

    def run(self) -> bool:
        validated = True
        missing_tiddlers = tw_get.filter_output("[all[missing]!is[system]]", port=self.port)
        if missing_tiddlers:
            validated = False
        for missing_tiddler in missing_tiddlers:
            backlinks = tw_get.filter_output(f"[[{missing_tiddler}]backlinks[]]", port=self.port)
            for backlink in backlinks:
                print(f"{terminal_style.YELLOW}{terminal_style.BOLD}{backlink}{terminal_style.RESET} has a broken link")
                if self.interactive:
                    tw_actions.open_tiddler(backlink)
                    input()

        if validated:
            print(f"{terminal_style.SUCCESS} Missing tiddlers resolved")
        else:
            print(f"{terminal_style.FAIL} Missing tiddlers")

        return validated


class Primary(QACheck):
    name = "Primary"

    def __init__(self, port, interactive=False, verbose=False):
        super().__init__(port)
        self.interactive = interactive
        self.verbose = verbose
        self.validated = True
        self.lineage_integrity = True
        self.sorting_bin = {
            "primary=tag": [],
            "primary≠tag": [],
            "primary∈tags": [],
            "primary∉tags": [],
            "¬∃primary∃tag": [],
            "¬∃primary∃tags": [],
            "¬∃primary¬∃tag": [],
            "∃primary¬∃tag": [],
        }

    def _reset_bins(self):
        for key in self.sorting_bin:
            self.sorting_bin[key] = []

    def _analyse(self):
        self._reset_bins()
        tw_fields = tw_get.tw_fields(["title", "neuro.primary", "tags"], "[!is[system]]", port=self.port)
        for tf in tw_fields:
            tags = tf.get("tags", [])

            if not tags:
                key = "∃primary¬∃tag" if "neuro.primary" in tf else "¬∃primary¬∃tag"
                self.sorting_bin[key].append(tf)
                continue

            if "neuro.primary" not in tf:
                key = "¬∃primary∃tag" if len(tags) == 1 else "¬∃primary∃tags"
                self.sorting_bin[key].append(tf)
            else:
                np = tf["neuro.primary"]
                if np in tags:
                    key = "primary=tag" if len(tags) == 1 else "primary∈tags"
                else:
                    key = "primary≠tag" if len(tags) == 1 else "primary∉tags"
                self.sorting_bin[key].append(tf)

        if self.verbose:
            counter = {key: len(val) for key, val in self.sorting_bin.items()}
            print("")
            print("-" * 30)
            DictUtils.represent(counter)

    def _verify_lineage(self):
        lineage_root = "$:/plugins/neuroforest/front/tags/Contents"
        lineage = tw_get.lineage(lineage_root, port=self.port)
        cycles = []
        for tid_title, lineage_item in lineage.items():
            if not lineage_item:
                pass
            elif len(lineage_item) >= 20:
                cycle = []
                for tt in lineage_item:
                    if tt not in cycle:
                        cycle.append(tt)
                if set(cycle) not in [set(c) for c in cycles]:
                    cycles.append(cycle)
                self.lineage_integrity = False
            elif lineage_item[0] != lineage_root:
                if not lineage_item[0].startswith("$:/"):
                    self.lineage_integrity = False
                    print(f"Lineage problem for tiddler {terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET}:")
                    print(" - ".join(lineage_item))

        if cycles:
            print("Cycles found:")
            for cycle in cycles:
                print("    " + " - ".join(cycle))

    def _resolve_simple(self):
        simple_tfs = self.sorting_bin["primary≠tag"] + self.sorting_bin["¬∃primary∃tag"]
        if not simple_tfs:
            return

        with _progress() as progress:
            task = progress.add_task("Primary corrections", total=len(simple_tfs))
            for tf in simple_tfs:
                title = tf["title"]
                progress.update(task, description=f"Primary: {_truncate(title).ljust(32)}")
                tiddler = tw_get.tiddler(title, port=self.port)
                tiddler.fields["neuro.primary"] = tf["tags"][0]
                if self.verbose:
                    if "neuro.primary" in tf:
                        progress.print(f"  Resolved simple error: {title}")
                    else:
                        progress.print(f"  Added primary: {title}")
                tw_put.tiddler(tiddler, port=self.port)
                progress.advance(task)
            progress.update(task, description="Primary".ljust(32))

    def _resolve_complex(self):
        complex_tfs = self.sorting_bin["primary∉tags"] + self.sorting_bin["¬∃primary∃tags"]
        if complex_tfs and not self.interactive:
            self.validated = False
            return

        for tf in complex_tfs:
            tid_title = tf["title"]
            tid_tags = sorted(tf["tags"])
            tw_actions.open_tiddler(tid_title)
            print(f"\n{'-' * 30}\nSetting primary for {terminal_style.BOLD}{tf['title']}{terminal_style.RESET}", end="")
            if "neuro.primary" in tf:
                print(f" (current {tf['neuro.primary']})")
            else:
                print()
            pyperclip.copy(tid_title)
            chose_title = terminal_components.selector(tid_tags)

            if chose_title:
                tiddler = tw_get.tiddler(tid_title, port=self.port)
                tiddler.fields["neuro.primary"] = chose_title
                tw_put.tiddler(tiddler, port=self.port)
            else:
                self.validated = False

    def run(self) -> bool:
        self.validated = True
        self.lineage_integrity = True
        self._analyse()
        self._resolve_simple()
        self._resolve_complex()

        # Re-analyse and verify lineage after corrections
        self._analyse()
        self._verify_lineage()

        if self.sorting_bin["∃primary¬∃tag"]:
            self.validated = False
            print(f"Rare error: {self.sorting_bin['∃primary¬∃tag']}")
        remaining_simple = self.sorting_bin["primary≠tag"] + self.sorting_bin["¬∃primary∃tag"]
        if remaining_simple:
            self.validated = False
            raise exceptions.InternalError("Automated corrections")
        remaining_complex = self.sorting_bin["primary∉tags"] + self.sorting_bin["¬∃primary∃tags"]
        if remaining_complex:
            self.validated = False
            print(f"{terminal_style.FAIL} Manual corrections were not resolved")
        if not self.lineage_integrity:
            self.validated = False
            print(f"{terminal_style.FAIL} Lineage problems")

        if self.validated:
            print(f"{terminal_style.SUCCESS} Primary resolved")

        return self.validated


class NeuroIDs(QACheck):
    name = "Neuro IDs"

    def __init__(self, port, verbose=False):
        super().__init__(port)
        self.verbose = verbose

    def run(self) -> bool:
        resolved = True

        unidentified = tw_get.tiddler_list("[!is[system]!has[neuro.id]]", port=self.port)
        if unidentified:
            with _progress() as progress:
                task = progress.add_task("Adding neuro.id", total=len(unidentified))
                for tiddler in unidentified:
                    progress.update(task, description=f"neuro.id: {_truncate(tiddler.title).ljust(32)}")
                    tw_put.tiddler(tiddler, port=self.port)
                    progress.advance(task)
                progress.update(task, description="neuro.id".ljust(32))

        all_nids = tw_get.filter_output("[has[neuro.id]get[neuro.id]]", port=self.port)
        seen = set()
        duplicates = set()
        for nid in all_nids:
            if nid in seen:
                duplicates.add(nid)
            else:
                seen.add(nid)

        if duplicates:
            resolved = False
            if self.verbose:
                print("The following neuro.id conflicts were found")
                for i, nid in enumerate(duplicates):
                    tid_titles = tw_get.filter_output(f"[search:neuro.id:literal[{nid}]]", port=self.port)
                    print(f"{i + 1}) {nid}:\n\t{'\n\t'.join(tid_titles)}")

        if not all(len(nid) == 36 for nid in seen):
            resolved = False
            print("neuro.id length variability detected")

        if resolved:
            print(f"{terminal_style.SUCCESS} Neuro ID")
        else:
            print(f"{terminal_style.FAIL} Neuro ID")

        return resolved


@click.command("qa", short_help="quality assurance")
@click.option("-i", "--interactive", is_flag=True)
@click.option("--port", default=os.getenv("PORT"))
@click.option("-v", "--verbose", is_flag=True)
@pass_environment
def cli(ctx, interactive, port, verbose):
    checks = [
        GhostTiddlers(port),
        ObjectSets(port),
        Roles(port),
        ValidateTags(port, interactive),
        MissingTiddlers(port, interactive),
        Primary(port, interactive, verbose),
        NeuroIDs(port, verbose),
    ]

    host = os.getenv("HOST", "127.0.0.1")
    if not network_utils.is_port_in_use(port, host):
        print(f"{terminal_style.FAIL} Service not running on {host}:{port}")
        raise SystemExit(1)

    results = [check.run() for check in checks]
    if not all(results):
        raise SystemExit(1)
    return True
