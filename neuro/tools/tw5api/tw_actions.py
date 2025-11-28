import os

from neuro.tools.tw5api import tw_api
from neuro.tools.terminal import style


def close_all(**kwargs):
    with tw_api.API(**kwargs) as api:
        response = api.put("/neuro/action/close-all")
        if response.status_code != 204:
            print(f"Error: {response.reason}")
        return response


def merge_tiddlers(title_list, **kwargs):
    with tw_api.API(**kwargs) as api:
        params = {
            "titles": title_list
        }
        response = api.put("/neuro/action/merge", params=params)
        if response.status_code != 204:
            print(f"Error: {response.reason}")
        return response


def open_tiddler(title, **kwargs):
    params = {
        "title": title
    }
    with tw_api.API(**kwargs) as api:
        response = api.put("/neuro/action/open", params=params)
        if response.status_code != 204:
            print(f"Error: {response.reason}")
        return response


def rename_tiddler(old_title, new_title, **kwargs):
    with tw_api.API(**kwargs) as api:
        params = {
            "oldTitle": old_title,
            "newTitle": new_title
        }
        response = api.put("/neuro/action/rename", params=params)
        if response.status_code == 200:
            print(style.SUCCESS, response.reason)
        else:
            print(style.FAIL, response.reason)
        return response


def replace_text(old_text, new_text, tw_filter="", **kwargs):
    with tw_api.API(**kwargs) as api:
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
    with tw_api.API(**kwargs) as api:
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
