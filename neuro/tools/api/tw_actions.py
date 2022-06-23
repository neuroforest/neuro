import os

from neuro.tools.api import tw_api
from neuro.tools.terminal import style


def merge_tiddlers(title_list, **kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    params = {
        "titles": title_list
    }

    response = api.put("/neuro/action/merge", params=params)
    if response.status_code != 204:
        print(f"Error: {response.reason}")
    return response


def rename_tiddler(old_title, new_title, **kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    params = {
        "oldTitle": old_title,
        "newTitle": new_title
    }
    response = api.put("/neuro/action/rename", params=params)
    if response.status_code != 204:
        print(f"Error: {response.reason}")
    return response


def replace_text(old_text, new_text, tw_filter="", **kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    params = {
        "oldText": old_text,
        "newText": new_text,
        "tw_filter": tw_filter
    }
    response = api.put("/neuro/action/replace", params=params)
    if response.status_code == 200:
        print(style.SUCCESS, response.reason)
    else:
        print(style.FAIL, response.reason)
    return response


def search(query, **kwargs):
    api = tw_api.get_api(**kwargs)
    if not api:
        return None

    params = {
        "query": query
    }
    response = api.put("/neuro/action/search", params=params)
    if response.status_code == 204:
        print(style.SUCCESS, response.reason)
        os.system("wmctrl -a NeuroWiki")
    else:
        print(style.FAIL, response.reason)
    return response


if __name__ == "__main__":
    search("testd")
