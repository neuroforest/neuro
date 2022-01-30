from neuro.tools.api import tw_api
from neuro.tools.terminal import style


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


def rename_tiddler(old_title, new_title):
    api = tw_api.get_api()
    if not api:
        return None

    params = {
        "oldTitle": old_title,
        "newTitle": new_title
    }
    response = api.put(f"/neuro/action/rename", params=params)
    if response.status_code != 204:
        print(f"Error: {response.reason}")


def replace_text(old_text, new_text, tw_filter):
    api = tw_api.get_api()
    if not api:
        return None

    params = {
        "oldText": old_text,
        "newText": new_text,
        "filter": tw_filter
    }
    response = api.put(f"/neuro/action/replace", params=params)
    if response.status_code == 200:
        print(style.SUCCESS, response.reason)
    else:
        print(style.FAIL, response.reason)
