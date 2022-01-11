"""
Locally running TiddlyWiki API.
"""

import json
import logging
import socket
import urllib.parse

import requests

from neuro.utils import internal_utils
from neuro.core.data.dict import DictUtils


TW_INDEX = dict()


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


class API:
    def __init__(self, port=internal_utils.PORT):
        self.port = port
        self.status = str()
        self.url = str()
        self.response = requests.Response()
        self.parsed_response = dict()

    def connect_url(self, url=internal_utils.URL):
        """
        Opens the connection to the file.
        :return:
        """
        if not is_port_in_use(self.port):
            msg = f"Port {self.port} is not running locally."
            logging.warning(f"Refused to connect to API: {msg}")
            self.status = "unavailable"
            return
        self.url = "http://" + url + ":" + str(self.port)
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
            DictUtils.display(self.response.__dict__)
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

        self.response = requests.put(
            full_url,
            data=kwargs.get("data", {}),
            headers=headers)

        return self.response


def get_api(port=internal_utils.PORT):
    if port not in TW_INDEX:
        logging.debug(f"Creating new API to port {port}.")
        tw_api = API(port)
        tw_api.connect_url()
    else:
        tw_api = TW_INDEX[port]

    api_status = tw_api.status
    if api_status == "available":
        logging.debug("API available.")
        return tw_api
    else:
        logging.error(f"API is {api_status}")
