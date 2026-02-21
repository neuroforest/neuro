"""
Neuro Query Language - NQL
"""

import os

import neo4j
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from neuro.base import NeuroBase
import neuro.base.nql.handlers as handlers
from neuro.base.nql.components import NqlParser


def dispatch(nb, query, parser):
    """Parse a query and execute the matching statement handler."""
    try:
        tree = parser.parse(query)
    except Exception as e:
        print(f"Syntax Error: {e}")
        return

    statement_type = tree.data
    try:
        handler = getattr(handlers, f"{statement_type}_handler")
    except AttributeError:
        print(f"No handler available for statement '{statement_type}'")
        return

    handler.handler(nb, tree)


def session():
    """
    NQL CLI session.

    Keyboard shortcuts:
    - Alt+Enter: send query
    - Ctrl+C: clear current input
    - Ctrl+D: exit session
    """
    nql_history_path = os.getenv("NQL_HISTORY", os.path.expanduser("~/.nql_history"))
    s = PromptSession(history=FileHistory(nql_history_path))
    parser = NqlParser()

    with NeuroBase() as nb:
        while True:
            try:
                query = s.prompt("⬤  ")
                dispatch(nb, query, parser)
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except neo4j.exceptions.CypherSyntaxError as e:
                print(f"Cypher syntax error: {e.message}")
