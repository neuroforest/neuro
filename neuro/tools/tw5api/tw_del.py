"""
DELETE wrapper.
"""

import os

from neuro.tools.tw5api import tw_api
from neuro.utils import exceptions, terminal_components


def tiddler(tid_title, **kwargs):
    with tw_api.API(**kwargs) as api:
        response = api.delete(f"/bags/default/tiddlers/{tid_title}")
        return response


def by_filter(tw_filter, confirm=True, **kwargs):
    with tw_api.API(**kwargs) as api:
        params = {"filter": tw_filter}
        if confirm and not terminal_components.bool_prompt(
                f"Delete by filter '{tw_filter}' on {api.host}:{api.port}?"):
            return False
        response = api.delete("/neuro", params=params, **kwargs)
        return response


def all_tiddlers(**kwargs):
    if "port" not in kwargs or kwargs["port"] is os.getenv("PORT"):
        raise exceptions.InternalError("Data loss event was blocked.")
    response = by_filter("[!is[system]]", confirm=False, **kwargs)
    return response
