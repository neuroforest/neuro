"""
Neuro Query Language - NQL
"""

import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

import neuro.base.nql.handlers as handlers
from neuro.base.nql.components import NqlParser


def session():
    """
    NQL CLI session.

    Keyboard shortcuts:
    - Alt+Enter: send query
    - Ctrl+C: clear current input
    - Ctrl+D: exit session
    """
    nql_history_path = os.getenv("NQL_HISTORY", os.path.expanduser("~/.nql_history"))
    history_file = FileHistory(nql_history_path)
    s = PromptSession(history=history_file)
    while True:
        try:
            query = s.prompt("⬤  ")
            try:
                tree = NqlParser().parse(query)
            except Exception as e:
                print(f"Syntax Error: {e}")
                continue

            statement_type = tree.data
            try:
                handler = getattr(handlers, statement_type)
                handler.handler(tree)
            except AttributeError:
                print(f"No handler available for statement '{statement_type}'")
                continue

        except KeyboardInterrupt:
            continue
        except EOFError:
            break
