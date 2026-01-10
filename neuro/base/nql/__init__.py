"""
Neuro Query Language - NQL
"""

import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from lark import Lark

import neuro.base.nql.handlers as handlers
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
    nql_grammar_path = internal_utils.get_path("resources") + "/nql-grammar.lark"
    with open(nql_grammar_path, "r") as f:
        nql_grammar = f.read()
    parser = Lark(nql_grammar, maybe_placeholders=False)
    while True:
        try:
            query = s.prompt(f"⬤  ")
            print(f"Query: {query}")
            try:
                tree = parser.parse(query)
            except Exception as e:
                print(f"Syntax Error: {e}")
                continue

            statement_type = tree.data
            print(statement_type)
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
