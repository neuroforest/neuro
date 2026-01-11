"""
Neuro Query Language - NQL
"""

import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from lark import Lark

import neuro.base.nql.handlers as handlers
from neuro.base.nql.components import NqlParser
from neuro.utils import internal_utils


def session():
    """
    NQL CLI session.

    Keyboard shortcuts:
    - Alt+Enter: send query
    - Ctrl+C: clear current input
    - Ctrl+D: exit session
    """
    history_file = FileHistory(os.path.expanduser("~/.nql_history"))
    s = PromptSession(history=history_file)
    while True:
        try:
            query = s.prompt(f"⬤  ")
            try:
                tree = NqlParser().parse(query)
            except Exception as e:
                print(f"Syntax Error: {e}")
                continue

            statement_type = tree.data
            try:
                handler = getattr(handlers, statement_type)
                handler.handler(tree)
            except AttributeError as e:
                print(f"No handler available for statement '{statement_type}'")
                continue

        except KeyboardInterrupt:
            continue
        except EOFError:
            break
