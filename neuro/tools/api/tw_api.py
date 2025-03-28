"""
Locally running TiddlyWiki API.
"""

import json
import logging
import os
import urllib.parse

import requests

from neuro.utils import network_utils
from neuro.core.data.dict import DictUtils


API_CACHE = dict()


class API:
    def __init__(self, port, url):
        self.url = f"http://{url}:{port}"
        self.response = requests.Response()
        self.parsed_response = dict()
        self.session = requests.Session()
        if not network_utils.is_port_in_use(port):
            msg = f"Port {port} is not running locally."
            logging.getLogger(__name__).warning(f"Refused to connect to API: {msg}")
            self.status = "unavailable"
        else:
            self.status = "available"

    def delete(self, path):
        full_url = self.url + urllib.parse.quote(path)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "TiddlyWiki"
        }
        self.response = self.session.delete(url=full_url, headers=headers)
        if self.response.status_code == 204:
            return True
        else:
            DictUtils.represent(self.response.__dict__)
            return False

    def get(self, path, **kwargs):
        full_url = self.url + urllib.parse.quote(path)
        params = kwargs.get("params", dict())
        logging.getLogger(__name__).debug(f"Request URL: {full_url}")
        self.response = self.session.get(url=full_url, params=params)
        self.parse()
        return {
            "parsed": self.parsed_response,
            **self.response.__dict__
        }

    def parse(self):
        # Getting the response content type.
        try:
            content_type = self.response.headers["Content-type"]
        except KeyError:
            logging.getLogger(__name__).debug(f"Could not parse response from {self.response.url}")
            self.parsed_response = dict()
            return

        if content_type.startswith("application/json"):
            self.parsed_response = json.loads(self.response.text)
        elif content_type == "text/html":
            self.parsed_response = self.response.text
        else:
            logging.error(f"Parsing for {content_type} not supported.")

    def put(self, path, **kwargs):
        full_url = self.url + urllib.parse.quote(path)
        # "User-Agent": "Mozilla/5.0",
        headers = {
            "X-Requested-With": "TiddlyWiki",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        logging.getLogger(__name__).debug(f"Put arguments:\n\tPath: {path}\n\tKwargs: {kwargs}")

        params = kwargs.get("params", dict())
        self.response = self.session.put(
            full_url,
            data=kwargs.get("data", {}),
            headers=headers,
            params=params)

        return self.response


def get_api(port=os.getenv("PORT"), url=os.getenv("URL"), **kwargs):
    global API_CACHE
    if port not in API_CACHE:
        logging.getLogger(__name__).debug(f"Creating new API to port {port}.")
        tw_api = API(port=port, url=url)
        API_CACHE[port] = tw_api
    else:
        tw_api = API_CACHE[port]

    api_status = tw_api.status
    if api_status == "available":
        return tw_api
    else:
        logging.getLogger(__name__).error(f"API is {api_status}")
