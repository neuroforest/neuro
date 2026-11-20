"""
General terminal interaction components.
"""

import re
from contextlib import contextmanager

from rich.console import Console

from neuro.core.file.text import Text
from neuro.utils import terminal_style


@contextmanager
def step(message, display=True):
    """Spinner during execution, ✔ on completion.

    Yields a status object with a ``.log(text)`` method that temporarily
    pauses the spinner, prints text, and resumes.
    """
    status = Console().status(f"[bold] {message}...", spinner="dots")
    status.start()

    def log(text):
        status.stop()
        print(text)
        status.start()

    status.log = log
    try:
        yield status
        status.stop()
        if display:
            print(f"{terminal_style.SUCCESS} {message}")
    except BaseException as e:
        status.stop()
        print(f"{terminal_style.FAIL} {message}: {e}")


def bool_prompt(question, default=None):
    """
    Bool prompt - yes converts to True, no to False.
    :param question: question to be assessed
    :param default: default value when Enter is pressed (True, False, or None for no default)
    :return: bool
    """
    if default is True:
        hint = "(Y/n)"
    elif default is False:
        hint = "(y/N)"
    else:
        hint = "(y/n)"
    while True:
        text = terminal_style.get_colored(f"{question} {hint}", "BOLD")
        res = input(text)
        if res.lower() == "y":
            return True
        elif res.lower() == "n":
            return False
        elif not res and default is not None:
            return default
        elif not res:
            continue
        else:
            return False


def bool_prompt_show(question, file_path):
    """
    Bool prompt - yes converts to True, no to False.
    :param question: question to be assessed
    :param file_path: path of the file to show
    :return: bool
    """
    while True:
        text = terminal_style.get_colored(question + " (y/n/s)", "BASE")
        res = input(text)
        if res.lower() == "y":
            return True
        elif res.lower() == "s":
            text = Text(file_path).get_text()
            print("\n" + text + "\n")
            continue
        elif not res:
            continue
        else:
            return False


_ANSI = re.compile(r"\033\[[0-9;]*m")


def _visible(val) -> int:
    """Printed width of a cell: its length without ANSI colour codes."""
    return len(_ANSI.sub("", str(val)))


def table(rows, header=None, indent=2):
    """Print aligned columns from a list of tuples with optional header.
    Cells may carry ANSI colour codes; columns align on what is printed."""
    if not rows:
        return
    all_rows = [header] + rows if header else rows
    widths = [max(_visible(r[i]) for r in all_rows) for i in range(len(all_rows[0]))]
    prefix = " " * indent

    def line(row):
        return "  ".join(f"{val}{' ' * (widths[i] - _visible(val))}" for i, val in enumerate(row))

    if header:
        print(f"{prefix}{terminal_style.BOLD}{line(header)}{terminal_style.RESET}")
    for row in rows:
        print(f"{prefix}{line(row)}")


def selector(options, metadata=None):
    indices = range(len(options))
    if metadata and len(options) == len(metadata):
        option_texts = [f"{options[i]} {metadata[i]}" for i in indices]
    else:
        option_texts = [str(o) for o in options]
    for i in indices:
        print(f"{i + 1} - {option_texts[i]}")
    temp = input(f"Select {' | '.join([str(i + 1) for i in indices])} | n (cancel) ")
    if temp == "n" or not temp:
        return None
    elif temp.isnumeric() and int(temp) - 1 in indices:
        return options[int(temp) - 1]
    else:
        print(f"{terminal_style.RED}Not valid: {temp}{terminal_style.RESET}")
        return None
