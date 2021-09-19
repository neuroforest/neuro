"""
PUT wrapper.
"""

import json
import logging

from neuro.tools.api import tw_api


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
	response = api.put("/recipes/default/tiddlers/" + api_tiddler["title"], data=tiddler_json)
	if response.status_code == 204:
		logging.debug(f"Put '{api_tiddler['title']}'")
	else:
		logging.error(f"Unhandled response status: {response.status_code}")
		logging.error(
			f"text: {response.text}\n"
			f"request: {response.request}"
			f"reason: {response.reason}")

	return response
