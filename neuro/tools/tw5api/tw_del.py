"""
DELETE wrapper.
"""

from neuro.tools.tw5api import tw_api


def tiddler(tid_title, **kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    response = api.delete(f"/bags/default/tiddlers/{tid_title}")
    return response
