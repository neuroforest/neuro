"""
Integrate NeuroWiki object into the local filesystem.
"""

import os.path

import click
import requests
from rich.console import Console
import tqdm

from neuro.core.tid import Tiddler, Tiddlers
from neuro.tools.tw5api import tw_get, tw_put
from neuro.tools.terminal.cli import pass_environment
from neuro.utils import terminal_components, terminal_style


def integrate_local(tid_title):
    tw_filter = f"[title[{tid_title}]]"
    lineage = tw_get.lineage(tw_filter=tw_filter)[tid_title]
    print(f"{terminal_style.BOLD}Lineage{terminal_style.RESET}: {" ➜  ".join(lineage[1:])}\n")
    neuro_tids_filter = " ".join(f"[[{element}]]" for element in lineage)
    neuro_tids = tw_get.neuro_tids(tw_filter=neuro_tids_filter)
    current_path = str()

    unrooted_neuro_tids = Tiddlers()
    for neuro_tid in reversed(neuro_tids):
        if "local" not in neuro_tid.fields:
            unrooted_neuro_tids.insert(0, neuro_tid)
        else:
            current_path = neuro_tid.fields["local"].replace("file://", "")
            break

    for neuro_tid in unrooted_neuro_tids:
        tid_title = neuro_tid.title
        if neuro_tid["title"].startswith("$"):
            continue

        if "local" in neuro_tid.fields:
            current_path = neuro_tid.fields["local"].replace("file://", "")
        else:
            if "name" in neuro_tid.fields:
                candidate_path = f"{current_path}/{neuro_tid.fields['name']}"
            else:
                name = Tiddler.get_local_name(tid_title)
                candidate_path = f"{current_path}/{name}"

            if os.path.isdir(candidate_path):
                if terminal_components.bool_prompt(f"Connect {candidate_path} to {terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET}?"):
                    neuro_tid.fields["local"] = f"file://{candidate_path}"
                    tw_put.neuro_tid(neuro_tid)
                    current_path = candidate_path
                else:
                    break
            else:
                if terminal_components.bool_prompt(f"Establish {candidate_path} for {terminal_style.YELLOW}{terminal_style.BOLD}{tid_title}{terminal_style.RESET}?"):
                    os.mkdir(candidate_path)
                    neuro_tid.fields["local"] = f"file://{candidate_path}"
                    tw_put.neuro_tid(neuro_tid)
                    current_path = candidate_path
                else:
                    break


def integrate_system_files(port):
    update_tids = False
    root_file_neuro_tids = tw_get.neuro_tids("[prefix[/]] [prefix[~]]", port=port)
    neuro_tids_to_update = Tiddlers()
    for neuro_tid in root_file_neuro_tids:
        if neuro_tid.title.startswith("~"):
            path = os.path.expanduser(neuro_tid.title)
        else:
            path = neuro_tid.title
        if os.path.isfile(path):
            if "file" not in neuro_tid.fields:
                neuro_tid.fields["file"] = f"file://{path}"
                neuro_tids_to_update.append(neuro_tid)
                update_tids = True
            else:
                if neuro_tid.fields["file"] != f"file://{path}":
                    print(f"Incorrect file path for {terminal_style.BOLD}{path}{terminal_style.RESET}")
        elif os.path.isdir(path):
            if "local" not in neuro_tid.fields:
                neuro_tid.fields["local"] = f"file://{path}"
                neuro_tids_to_update.append(neuro_tid)
                update_tids = True
            else:
                if neuro_tid.fields["local"] != f"file://{path}":
                    print(f"Incorrect local path for {terminal_style.BOLD}{path}{terminal_style.RESET}")
        else:
            pass
            print(f"Missing file: {path}")

    if update_tids:
        width = min([max([len(neuro_tid.title) for neuro_tid in neuro_tids_to_update]), 24])
        with tqdm.tqdm(total=len(neuro_tids_to_update)) as pbar:
            for neuro_tid in neuro_tids_to_update:
                pbar.set_description(neuro_tid.title.ljust(width)[:width])
                tw_put.neuro_tid(neuro_tid, port=port)
                pbar.update(1)
            pbar.set_description("")


def check_local_integration(port, verbose=True):
    """
    Check all `local` fields to point to existing files.
    :param port:
    :param verbose:
    :return:
    """
    validated = True

    locally_integrated_neuro_tids = tw_get.neuro_tids("[has[local]]", port=port)

    for neuro_tid in locally_integrated_neuro_tids:
        local_path = neuro_tid.fields["local"]
        if not os.path.isdir(local_path.replace("file://", "")):
            print(f"Local integration for {terminal_style.BOLD}{neuro_tid.title}{terminal_style.RESET} is broken.")
            validated = False

    if verbose:
        if validated:
            print(f"{terminal_style.SUCCESS} Local integration")
        else:
            print(f"{terminal_style.FAIL} Local integration broken")

    return validated


def check_images(port, verbose=True):
    """
    Check all `img` fields to point to existing files.
    :param port:
    :param verbose:
    :return:
    """
    validated = True
    img_neuro_tids = tw_get.neuro_tids("[has[img]]", port=port)

    for neuro_tid in tqdm.tqdm(img_neuro_tids):
        img_path = neuro_tid.fields["img"]
        if img_path.startswith("file://"):
            if not os.path.isfile(img_path.replace("file://", "")):
                print(f"Image integration for {terminal_style.BOLD}{neuro_tid.title}{terminal_style.RESET} is broken.")
                validated = False
        elif img_path.startswith("http://") or img_path.startswith("https://"):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
            }
            try:
                response = requests.head(img_path, headers=headers, allow_redirects=True)
                if response.status_code != 200:
                    print(f"Status code: {response.status_code}")
                    print(f"Tiddler: {neuro_tid.title}")
                    print(f"URL: {img_path}")

            except requests.RequestException as e:
                print(f"Request failed: {e}")
            validated = False

    return validated


@click.command("local", short_help="local file management")
@click.argument("tid_title", required=False)
@click.option("-i", "--img", is_flag=TypeError)
@click.option("-q", "--quality", is_flag=True)
@click.option("-p", "--port", type=int, default=os.getenv("PORT"))
@pass_environment
def cli(ctx, tid_title, img, quality, port):
    """
    :param ctx:
    :param tid_title:
    :param img:
    :param quality:
    :param port:
    """
    if img:
        validated = check_images(port=os.getenv("PORT"))
        return validated

    if quality:
        with Console().status("Integrating system files...", spinner="dots"):
            integrate_system_files(port)
            validated = check_local_integration(port)
        return validated

    if tid_title:
        if not tw_get.is_tiddler(tid_title):
            print(f"No object found: {tid_title}")
        else:
            integrate_local(tid_title)
    return None
