"""
Terminal styling.
"""

import logging
import sys
import time
from contextlib import contextmanager

from rich.console import Console


# COLOR SCHEME
TERMINAL_DARK = 235
TERMINAL_LIGHT = 122

BOLD = "\033[1m"

# COLOR CODES
BASE = "\033[1;37m"
GREEN = "\33[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"

RESET = "\033[0m"

SUCCESS = GREEN + "✔" + RESET
FAIL = RED + "✘" + RESET


@contextmanager
def step(message):
    """Spinner during execution, ✔ on completion."""
    with Console().status(f"[bold] {message}...", spinner="dots"):
        yield
    print(f"{SUCCESS} {message}")


PROG_ICON = [
    "======================================",
    "||..................................||",
    "||..@@@@@@..................@@@@@@..||",
    "||.@@@@@@@@.@@@@@@@@@@@@@@.@@@@@@@@.||",
    "||..@@@@@@..................@@@@@@..||",
    "||......@@..................@@......||",
    "||........@@..............@@........||",
    "||..........@@..........@@..........||",
    "||............@@......@@............||",
    "||..............@@@@@@..............||",
    "||.............@@@@@@@@.............||",
    "||..............@@@@@@..............||",
    "||................@@................||",
    "||................@@................||",
    "||................@@................||",
    "||................@@................||",
    "||..............@@@@@@..............||",
    "||.............@@@@@@@@.............||",
    "||..............@@@@@@..............||",
    "||..................................||",
    "||..... WELCOME TO NeuroForest .....||",
    "||..................................||",
    "======================================"
]


def encolor_text(text, color_code, mode=""):

    # Check the code.
    if not isinstance(color_code, int) or color_code not in range(256):
        logging.error(f"Color code given is not correct: {color_code}")
        return text

    mu_codes = get_markup(color_code, mode=mode)
    text = mu_codes[0] + text + mu_codes[1]
    return text


def get_colored(text, color):
    prefix = globals()[color]
    suffix = RESET

    colored_text = prefix + text + suffix
    return colored_text


def get_markup(color_code, mode="fg"):
    """
    Get markup codes to append around the text to print in custom color.
    :param color_code: integer 0 - 255
    :param mode:
        - fg, apply color to the character font
        - bg, apply color to the character background
    """
    if mode == "fg":
        mu_code = "\33[38;5;"
    elif mode == "bg":
        mu_code = "\33[48;5;"
    else:
        logging.warning(f"Mode is not supported: {mode}")
        sys.exit()

    mu_code_start = mu_code + str(color_code) + "m"
    mu_code_end = "\33[0m"

    return mu_code_start, mu_code_end


def intro(speed=0.005):
    color_dark = TERMINAL_DARK
    color_light = TERMINAL_LIGHT
    prog_icon = PROG_ICON
    for string in prog_icon:
        print("\n", end="")
        for char in string:
            if char == ".":
                text = encolor_text(char, color_light, mode="bg")
            else:
                text = encolor_text(char, color_dark, mode="bg")

            print(text, end="")
            time.sleep(speed)
    print("\n\n")


def print_terminal_wait(text, time_s):
    sys.stdout.write(text)
    sys.stdout.flush()
    time.sleep(time_s)


def preview_color_codes():
    """
    Prints out all the codes in respective colors.
    """
    def print_six(row, mode=""):
        for col in range(6):
            color = row * 6 + col + 4
            if color >= 0:
                mu_code = get_markup(color, mode=mode)
                color_str = mu_code[0] + "{:3d}".format(color) + mu_code[1]
                print(color_str, end=" ")
            else:
                print("   ", end=" ")

    for row in range(-1, 42):
        print_six(row, mode="fg")
        print("", end=" ")
        print_six(row, mode="bg")
        print()
