"""
Locally running TiddlyWiki API.
"""

import json
import logging
import os
import urllib.parse

import requests

from neuro.utils import network_utils, config
from neuro.core.data.dict import DictUtils


config.load_env_files()
TW_INDEX = dict()


class API:
    def __init__(self, port, url):
        self.url = f"http://{url}:{port}" 
        self.response = requests.Response()
        self.parsed_response = dict()
        if not network_utils.is_port_in_use(port):
            msg = f"Port {port} is not running locally."
            logging.warning(f"Refused to connect to API: {msg}")
            self.status = "unavailable"
        else:
            self.status = "available"

    def delete(self, path):
        full_url = self.url + urllib.parse.quote(path)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "TiddlyWiki"
        }
        self.response = requests.delete(url=full_url, headers=headers)
        if self.response.status_code == 204:
            return True
        else:
            DictUtils.represent(self.response.__dict__)
            return False

    def get(self, path, **kwargs):
        full_url = self.url + urllib.parse.quote(path)
        params = kwargs.get("params", dict())
        logging.debug(f"Request URL: {full_url}")
        self.response = requests.get(url=full_url, params=params)
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
            logging.debug(f"Could not parse response from {self.response.url}")
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
        logging.debug(f"Put arguments:\n\tPath: {path}\n\tKwargs: {kwargs}")

        params = kwargs.get("params", dict())
        self.response = requests.put(
            full_url,
            data=kwargs.get("data", {}),
            headers=headers,
            params=params)

        return self.response


def get_api(port=os.getenv("PORT"), url=os.getenv("URL"), **kwargs):
    if port not in TW_INDEX:
        logging.debug(f"Creating new API to port {port}.")
        tw_api = API(port=port, url=url)
    else:
        tw_api = TW_INDEX[port]

    api_status = tw_api.status
    if api_status == "available":
        logging.debug("API available.")
        return tw_api
    else:
        logging.error(f"API is {api_status}")
