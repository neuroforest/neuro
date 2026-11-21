"""
General terminal interaction components.
"""

import re
import shutil
import sys
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


def table(rows, header=None, indent=2, shrink=None, width=None):
    """Print aligned columns from a list of tuples with optional header.
    Cells may carry ANSI colour codes; columns align on what is printed.

    `shrink`: the index of one free-text column, so every row stays on one
    line. Its cell runs over the cells to its right when those are all empty,
    up to the terminal's edge; only where something follows it is it held to
    the column, and cut with an ellipsis when the row would not fit. So one
    long value further right does not squeeze every row. `width` overrides the
    terminal's; output that is not a terminal (a pipe, a file) is never cut.
    Lines carry no trailing padding."""
    if not rows:
        return
    all_rows = [header] + rows if header else rows
    widths = [max(_visible(r[i]) for r in all_rows) for i in range(len(all_rows[0]))]
    prefix = " " * indent
    if shrink is not None and width is None and sys.stdout.isatty():
        width = shutil.get_terminal_size().columns

    def alone(row):
        return shrink is not None and not any(str(v) for v in row[shrink + 1:])

    if shrink is not None:
        held = [_visible(r[shrink]) for r in all_rows if not alone(r)]
        widths[shrink] = max(held, default=0)
        if width:
            over = indent + sum(widths) + 2 * (len(widths) - 1) - width
            if over > 0:
                widths[shrink] = max(widths[shrink] - over, 12)

    def cut(val, room):
        return val if _visible(val) <= room else _ANSI.sub("", val)[:max(room - 1, 0)].rstrip() + "…"

    def line(row):
        cells = []
        for i, val in enumerate(row):
            val = str(val)
            if i == shrink and alone(row):
                room = width - indent - sum(widths[:i]) - 2 * i if width else _visible(val)
                cells.append(cut(val, max(room, 12)))
                break
            if i == shrink:
                val = cut(val, widths[i])
            cells.append(f"{val}{' ' * (widths[i] - _visible(val))}")
        return "  ".join(cells).rstrip()

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
