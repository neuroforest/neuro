"""
Locally running TiddlyWiki API.
"""

import json
import logging
import os
import urllib.parse

import requests

from neuro.utils import network_utils, exceptions
from neuro.core.data.dict import DictUtils


class API:
    def __init__(self, port=None, host=None):
        self.port = port or os.getenv("PORT")
        self.host = host or os.getenv("HOST")
        if self.port is None:
            raise exceptions.NoAPI(
                "API port is required. Pass it via the 'port' argument"
                " or set the 'PORT' environment variable."
            )
        if self.host is None:
            raise exceptions.NoAPI(
                "API URL is required. Pass it via the 'url' argument"
                " or set the 'URL' environment variable."
            )
        self.url = f"http://{self.host}:{self.port}"
        self.response = requests.Response()
        self.parsed_response = dict()
        self.session = requests.Session()

    def __enter__(self):
        if not network_utils.is_port_in_use(self.port, self.host):
            raise exceptions.NoAPI(f"Service not running on {self.host}:{self.port}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

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
        try:
            self.response = self.session.get(url=full_url, params=params)
            self.response.encoding = "utf-8"
            self.parse()
            return {
                "parsed": self.parsed_response,
                **self.response.__dict__
            }
        except exceptions.NoAPI:
            return ""

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

