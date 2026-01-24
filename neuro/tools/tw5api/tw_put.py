"""
PUT wrapper.
"""

import json
import logging

from neuro.core import Tiddler, TiddlerList
from neuro.tools.tw5api import tw_api


def fields(tw_fields, **kwargs):
    """
    Api tiddler is not even necessary.
    :param tw_fields: dict, with obligatory key "title"
    :param preserve: preserve existing fields, not changing modified
    :return:
    """
    with tw_api.API(**kwargs) as api:

        tiddler_json = json.dumps(tw_fields)
        response = api.put("/neuro/tiddlers/" + tw_fields["title"],
                           data=tiddler_json, params=kwargs.get("params", dict()))
        if response.status_code == 204:
            logging.debug(f"Put '{tw_fields['title']}'")
        else:
            logging.error(f"Unhandled response status: {response.status_code}")
            logging.error(
                f"text: {response.text}\n"
                f"request: {response.request}"
                f"reason: {response.reason}")

        return response


def tiddler(tid: Tiddler, **kwargs):
    tid_fields = tid.fields
    tid_fields["title"] = tid.title
    if "neuro.id" not in tid_fields:
        tid_fields["neuro.id"] = tid.uuid
    fields(tid_fields, **kwargs)


def tiddler_list(tid_list: TiddlerList, **kwargs):
    for tid in tid_list:
        tiddler(tid, **kwargs)
