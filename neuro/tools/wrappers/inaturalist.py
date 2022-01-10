import json
import requests
import urllib.parse

from neuro.utils import exceptions


def get_request(endpoint: str, params: dict, **kwargs):
	"""
	Make an API call to iNaturalist API.
	Reference: https://www.inaturalist.org/pages/api+reference

	:param endpoint: API endpoint
	:param params:
	:param kwargs:
	:return: data dict
	"""
	inaturalist_api = "https://api.inaturalist.org/v1/"
	url = urllib.parse.urljoin(inaturalist_api, endpoint)
	headers = {'Accept': 'application/json'}

	res = requests.get(url, params, headers=headers, **kwargs)
	status_code = res.status_code
	if status_code == 200:
		data: list = json.loads(res.text)["results"]
		return data
	elif status_code == 404:
		raise exceptions.InvalidURL(url)
	else:
		raise exceptions.UnhandledStatusCode(str(status_code))


def request_observation(observation_id, **kwargs):
	endpoint = f"observations/{observation_id}"
	data = get_request(endpoint, kwargs.get("params", {}))
	return data[0]

