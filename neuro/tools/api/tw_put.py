"""
PUT wrapper.
"""

import json
import logging

from neuro.tools.api import tw_api


def fields(tw_fields, **kwargs):
    """
    Put fields to existing tiddler.
    :param tw_fields: dictionary of fields
    :return:
    """
    if "title" not in tw_fields:
        log.error("Missing field: title")
        return
    else:
        tid_title = tw_fields.pop("title")

    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    fields_json = json.dumps(tw_fields)
    response = api.put("/neuro/fields/" + tid_title, data=fields_json)
    if response.status_code == 204:
        logging.debug(f"Put fields to '{tid_title}'")
    else:
        logging.error(f"Unhandled response status: {response.status_code}")
        logging.error(
            f"text: {response.text}\n"
            f"request: {response.request}"
            f"reason: {response.reason}")

    return response


def tiddler(api_tiddler, **kwargs):
    """
    Api tiddler is not even necessary.
    :param api_tiddler:
    :return:
    """
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    tiddler_json = json.dumps(api_tiddler)
    response = api.put("/neuro/tiddlers/" + api_tiddler["title"], data=tiddler_json)
    if response.status_code == 204:
        logging.debug(f"Put '{api_tiddler['title']}'")
    else:
        logging.error(f"Unhandled response status: {response.status_code}")
        logging.error(
            f"text: {response.text}\n"
            f"request: {response.request}"
            f"reason: {response.reason}")

    return response


def neuro_tid(nt, **kwargs):
    tid = nt.fields
    tid["title"] = nt.title
    if "neuro.id" not in tid:
        tid["neuro.id"] = nt.uuid
    tiddler(tid, **kwargs)
