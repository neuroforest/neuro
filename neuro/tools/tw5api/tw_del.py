"""
DELETE wrapper.
"""

from neuro.tools.tw5api import tw_api


def tiddler(tid_title, **kwargs):
    with tw_api.API(**kwargs) as api:
        response = api.delete(f"/bags/default/tiddlers/{tid_title}")
        return response
