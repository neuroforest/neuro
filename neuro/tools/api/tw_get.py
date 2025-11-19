"""
GET wrapper.
"""

import logging
import os
import webbrowser

from neuro.core.tid import NeuroTid, NeuroTids
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
    response = api.get("/recipes/default/tiddlers.json", **kwargs)
    return response["parsed"]


def filter_output(tw_filter, **kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    url = "/neuro/filter"
    params = {"filter": tw_filter}
    response = api.get(url, params=params, **kwargs)
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


def lineage(root="$:/plugins/neuroforest/front/tags/Contents", tw_filter="[!is[system]]",
            scope_filter="[!is[system]]", limit=20, **kwargs):
    """
    Get lineage of all tiddlers included by the filter.
    :param root: the root returned lineages
    :param tw_filter: get lineage for these objects
    :param scope_filter: include these objects in the lineage
    :param limit: overflow and cycle protection limit
    :return:
    :rtype: dict
    """
    query_fields = tw_fields(["title", "neuro.primary"], tw_filter, **kwargs)
    scope_fields = tw_fields(["title", "neuro.primary"], scope_filter, **kwargs)
    query = dict()
    for i in query_fields:
        query[i["title"]] = i
    scope = dict()
    for i in scope_fields:
        scope[i["title"]] = i

    lineage_dict = dict()
    for tid_title, tf in query.items():
        lineage_item = list()
        if "neuro.primary" not in tf:
            logging.getLogger(__name__).info(f"Lineage chain broken at {tid_title}")
            continue

        current_tid_title = tid_title
        count = 0
        while True:
            if current_tid_title == root:
                lineage_item.insert(0, current_tid_title)
                break
            elif current_tid_title not in scope:
                logging.getLogger(__name__).info(f"Out of scope {current_tid_title}")
                lineage_item = list()
                break
            elif count >= limit:
                break
            else:
                if "neuro.primary" in scope[current_tid_title]:
                    lineage_item.insert(0, current_tid_title)
                    current_tid_title = scope[current_tid_title]["neuro.primary"]
                    count += 1
                else:
                    logging.getLogger(__name__).info(f"Out of scope {current_tid_title}")
                    lineage_item = list()
                    break
        if lineage_item:
            lineage_dict[tid_title] = lineage_item

    return lineage_dict


def neuro_tid(tid_title, **kwargs):
    t = tiddler(tid_title, **kwargs)
    if t:
        nt = NeuroTid.from_tiddler(t)
        return nt
    else:
        return NeuroTid(tid_title)


def neuro_tids(tw_filter, **kwargs):
    titles = tw_fields(["title"], tw_filter=tw_filter, **kwargs)
    nts = NeuroTids()
    for t in titles:
        tid_title = t["title"]
        nt = neuro_tid(tid_title, **kwargs)
        nts.append(nt)

    return nts


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


def tid_titles(tw_filter, **kwargs):
    tfs = tw_fields(["title"], tw_filter, **kwargs)
    title_list = list()
    for tf in tfs:
        title_list.append(tf["title"])
    return title_list


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
    :return: lod
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
    parsed_response = api.get(url, params=params, **kwargs)["parsed"]
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

    logging.getLogger(__name__).info(f"Collecting wiki HTML from {api.url}")
    tw_html = api.get("/")["parsed"]
    return tw_html
