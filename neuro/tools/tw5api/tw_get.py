"""
GET wrapper.
"""

import logging

from neuro.core.tid import Tiddler, TiddlerList
from neuro.tools.tw5api import tw_api
from neuro.utils import exceptions


def all_fields(**kwargs):
    """
    Return a list of tiddler fields, except 'text'.
    :return: list of dictionaries
    """
    with tw_api.API(**kwargs) as api:
        print("Collecting ... from {}".format(api.url))
        response = api.get("/recipes/default/tiddlers.json", **kwargs)
        return response["parsed"]


def filter_output(tw_filter, **kwargs):
    with tw_api.API(**kwargs) as api:
        params = {"filter": tw_filter}
        response = api.get("/neuro/filter", params=params, **kwargs)
        return response["parsed"]


def info(**kwargs):
    with tw_api.API() as api:
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
        fields(tid_title, **kwargs)
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


def tiddler(tid_title, **kwargs):
    t = fields(tid_title, **kwargs)
    if t:
        nt = Tiddler.from_fields(t)
        return nt
    else:
        return Tiddler(tid_title)


def tiddler_list(tw_filter, **kwargs):
    titles = tw_fields(["title"], tw_filter=tw_filter, **kwargs)
    tid_list = TiddlerList()
    for t in titles:
        tid_title = t["title"]
        tid = tiddler(tid_title, **kwargs)
        tid_list.append(tid)

    return tid_list


def server_status(**kwargs):
    with tw_api.API(**kwargs) as api:
        parsed_response = api.get("/status")
        return parsed_response


def tid_titles(tw_filter, **kwargs):
    tfs = tw_fields(["title"], tw_filter, **kwargs)
    title_list = list()
    for tf in tfs:
        title_list.append(tf["title"])
    return title_list


def fields(tid_title, **kwargs):
    """
    :param tid_title:
    """
    with tw_api.API(**kwargs) as api:
        response = api.get(f"/neuro/tiddlers/{tid_title}")

        if response["status_code"] == 200:
            return response["parsed"]
        elif response["status_code"] == 404:
            raise exceptions.TiddlerDoesNotExist(tid_title)
        else:
            raise exceptions.UnhandledStatusCode(response["status_code"])


def tw_fields(field_selection: list, tw_filter: str, **kwargs):
    """
    Filter tiddlers by `tw_filter` and extract `fields`.
    :param field_selection:
    :param tw_filter:
    :return: lod
    """
    with tw_api.API(**kwargs) as api:
        params = dict()
        if field_selection:
            params["fields"] = field_selection
        if tw_filter:
            params["filter"] = tw_filter
        parsed_response = api.get("/neuro/fields.json", params=params, **kwargs)["parsed"]
        return parsed_response


def wiki(**kwargs):
    """
    Returns the full wiki html.
    :return:
    """
    with tw_api.API(**kwargs) as api:
        logging.getLogger(__name__).info(f"Collecting wiki HTML from {api.url}")
        tw_html = api.get("/")["parsed"]
        return tw_html


def export_wiki(wiki_path, **kwargs):
    wiki_html = wiki(**kwargs)
    with open(wiki_path, "w+", encoding="utf-8") as f:
        f.write(wiki_html)
