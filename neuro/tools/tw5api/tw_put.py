"""
PUT wrapper.
"""

import json
import logging

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


def tiddler(nt, **kwargs):
    tid = nt.fields
    tid["title"] = nt.title
    if "neuro.id" not in tid:
        tid["neuro.id"] = nt.uuid
    fields(tid, **kwargs)
