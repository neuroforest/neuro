"""
DELETE wrapper.
"""

from neuro.tools.api import tw_api


def tiddler(tid_title):
	api = tw_api.get_api()
	if not api:
		return None

	response = api.delete("/bags/default/tiddlers/" + tid_title)
	return response
