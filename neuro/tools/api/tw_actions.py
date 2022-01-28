import urllib.parse

from neuro.tools.api import tw_api


def rename_tiddler(old_title, new_title):
    api = tw_api.get_api()
    if not api:
        return None

    params = {
        "old": old_title,
        "new": new_title
    }
    response = api.put(f"/neuro/action/rename", params=params)
    if response.status_code != 204:
        print(f"Error: {response.reason}")


def merge_tiddlers(title_list):
    api = tw_api.get_api()
    if not api:
        return None

    params = {
        "titles": title_list
    }

    response = api.put(f"/neuro/action/merge", params=params)
    if response.status_code != 204:
        print(f"Error: {response.reason}")
