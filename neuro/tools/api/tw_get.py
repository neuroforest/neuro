"""
GET wrapper.
"""

import logging
import os
import webbrowser

from neuro.core.tid import NeuroTid
from neuro.tools.api import tw_api
from neuro.utils import exceptions


def all_tiddlers(**kwargs):
    """
    Return a list of tiddlers.
    :return: list of dictionaries
    """
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    print("Collecting ... from {}".format(api.url))
    response = api.get("/recipes/default/tiddlers.json")
    return response["parsed"]


def info(**kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    response = api.get("/neuro/info")
    if response["status_code"] == 200:
        return response["parsed"]
    else:
        raise exceptions.UnhandledStatusCode(response["status_code"])


def is_tiddler(tid_title, **kwargs):
    """
    Checks if the tiddler is accessible through the API.

    :param tid_title:
    :return: bool
    """

    try:
        tiddler(tid_title, **kwargs)
        return True
    except exceptions.TiddlerDoesNotExist:
        return False


def neuro_tid(tid_title):
    t = tiddler(tid_title)
    if t:
        nt = NeuroTid.from_tiddler(t)
        return nt
    else:
        return NeuroTid(tid_title)


def rendered_tiddler(tid_title):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    parsed_response = api.get("/{}".format(tid_title), content_type="text/html")
    path = os.path.abspath("temp.html")
    url = "file://" + path

    with open(path, "w", encoding="utf-8") as f:
        f.write(parsed_response)

    # Opening the rendered tiddler in the web browser.
    webbrowser.open(url)


def server_status():
    api = tw_api.get_api()
    if not api:
        return None

    parsed_response = api.get("/status")
    return parsed_response


def tiddler(tid_title, **kwargs):
    """
    Returns tiddler data.
    :param tid_title:
    :return: tid
    """
    api = tw_api.get_api(**kwargs)
    if not api:
        raise exceptions.NoAPI()
    response = api.get(f"/neuro/tiddlers/{tid_title}")

    if response["status_code"] == 200:
        return response["parsed"]
    elif response["status_code"] == 404:
        raise exceptions.TiddlerDoesNotExist(tid_title)
    else:
        raise exceptions.UnhandledStatusCode(response["status_code"])


def tw_fields(fields: list, tw_filter: str, **kwargs):
    """
    Filter tiddlers by `tw_filter` and extract `fields`.
    :param fields:
    :param tw_filter:
    :return:
    """
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    url = "/neuro/fields.json"
    params = dict()
    if fields:
        params["fields"] = fields
    if tw_filter:
        params["filter"] = tw_filter
    parsed_response = api.get(url, params=params)["parsed"]
    return parsed_response


def tw_index(tw_filter=None, **kwargs):
    """
    Return a list of objects representing tiddler including shadow.
    {
        "tmap.id": "gkqo50qg803yjqeg95y",
        "tags": ["tag1", "long tag 2"],
        "title": "Example"
    }
    :param tw_filter:
    :return:
    :rtype: list
    """
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    url = "/neuro/index.json"
    params = dict()
    if tw_filter:
        params["filter"] = tw_filter
    response = api.get(url, params=params)
    return response["parsed"]


def wiki(**kwargs):
    """
    Returns the full wiki html.
    :return:
    """
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    logging.info(f"Collecting wiki HTML from {api.url}")
    tw_html = api.get("/")["parsed"]
    return tw_html
