"""
Object associated with TiddlyWiki5 and related data.
"""
import json
import logging
import os
import re
from pathlib import Path
import shutil
import subprocess

from bs4 import BeautifulSoup as Soup
from bs4.element import Tag

from neuro.core import Node, Moment
from neuro.core.file.text import TextHtml
from neuro.utils import exceptions, internal_utils, network_utils


class Tiddler(Node):
    """
    Tiddler is a Python representation of tiddler that is an element of
    the NeuroForest platform.
    There are 3 fundamental object properties:
        - uuid - inherited from Node
        - title - tiddler title, also serves as identifier
        - fields - a dictionary of all fields, some with special handling (tags, list)
    """
    def __init__(self, tid_title="", fields=None, **kwargs):
        super().__init__(["Tiddler"], **kwargs)
        self.title = tid_title
        if fields and isinstance(fields, dict):
            self.fields = fields
        else:
            self.fields = dict()
        self.properties = self.fields

    def __bool__(self):
        return bool(self.title)

    def __delitem__(self, key):
        if key in self:
            del self.fields[key]

    def __eq__(self, other):
        if not isinstance(other, Tiddler):
            return False

        ignore_keys = ["modified", "revision"]
        self_fields, other_fields = self.fields.copy(), other.fields.copy()
        for key in ignore_keys:
            try:
                del self_fields[key]
            except KeyError:
                pass
            try:
                del other_fields[key]
            except KeyError:
                pass

        return self.title == other.title and self_fields == other_fields

    def __getitem__(self, key):
        if key in ["title", "uuid", "fields"]:
            return super().__getitem__(key)
        else:
            return self.fields[key]

    def __contains__(self, key):
        d = {
            **self.fields,
            "title": self.title,
            "uuid": self.uuid
        }
        if key in d:
            return True
        else:
            return False

    def __repr__(self):
        return f"\n{self.__str__()}\n{super().__repr__()}"

    def __setitem__(self, key, value):
        if key in ["title", "edges", "uuid", "fields"]:
            super().__setitem__(key, value)
        else:
            self.fields[key] = value

    def __str__(self):
        return f"<Tiddler title=\"{self.title}\">"

    def add_fields(self, fields, overwrite=False):
        """
        :param fields:
        :param overwrite: overrides existing fields
        :return:
        """
        for field_name, field_value in fields.items():
            if field_name in self.fields:
                if overwrite and self.fields != field_value:
                    logging.warning(f"Overriding field: {field_name}  - {self.fields[field_name]} -> {field_value}")
                    self.fields[field_name] = field_value
            else:
                self.fields[field_name] = field_value

    def add_tag(self, tags):
        if "tags" in self.fields:
            if not isinstance(self.fields["tags"], list):
                logging.error("Incorrect data type of field 'tags', should be list.")
                return
        else:
            self.fields["tags"] = list()
        if isinstance(tags, str):
            self.fields["tags"].append(tags)
        elif isinstance(tags, list):
            self.fields["tags"].extend(tags)

    @classmethod
    def from_html(cls, html):
        if isinstance(html, Tag):
            div_element = html
        elif isinstance(html, str):
            soup = Soup(html, "html.parser")
            div_element = soup.find("div")
            if not div_element:
                raise exceptions.InternalError(f"HTML not structured properly: {html}")
        else:
            raise TypeError(f"HTML type not supported: {type(html)}")

        fields = div_element.attrs
        fields["text"] = div_element.text
        try:
            tid_title = fields["title"]
            return cls(tid_title, fields)
        except KeyError:
            logging.error(f"No title in HTML: {html}")
            return cls()

    @classmethod
    def from_fields(cls, fields):
        """
        :param fields:
        :return:
        """
        try:
            tid_title = fields["title"]
        except KeyError:
            raise exceptions.MissingTitle()

        if "created" in fields:
            created = fields["created"]
            pattern_utc = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z"
            pattern_tw5 = r"\d{17}"
            if re.match(pattern_utc, created):
                fields["created"] = Moment(created, form="utc").to_tid_val()
            elif re.match(pattern_tw5, created):
                fields["created"] = Moment(created, form="tw5").to_tid_val()
            else:
                logging.error(f"The format of field 'created' is not recognized: {created}")

        return cls(tid_title=tid_title, fields=fields)

    @staticmethod
    def get_tid_file_name(tid_title):
        """
        Replace special characters in the file name, for example: ':', '/' ,'\', ...
        NOTE: For testing purposes this is a static method.
        """
        tid_file_name = tid_title
        tid_file_name = re.sub(r"\/|\\", "_", tid_file_name)
        tid_file_name = re.sub(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])$", "_$1_", tid_file_name, flags=re.IGNORECASE)
        tid_file_name = re.sub(r"^ +", "_", tid_file_name)
        tid_file_name = re.sub(r"[\x00-\x1f\x80-\x9f]", "_", tid_file_name)
        tid_file_name = re.sub(r"<|>|~|\:|\"|\||\?|\*|\^", "_", tid_file_name)

        if len(tid_file_name) > 200:
            tid_file_name = tid_file_name[:200]

        return tid_file_name

    def to_text(self):
        """
        Determine tid file text.
        """
        if "text" in self.fields:
            tid_text = self.fields["text"]
        else:
            tid_text = None

        text = str()
        for field in sorted(self.fields):
            if field in self.fields and field != "text":
                text += f"{field}: {self.fields[field]}\n"

        if tid_text:
            text += f"\n{tid_text}"
        else:
            text = text.strip()

        return text

    def write(self, directory="", path=""):
        """Serialize Tiddler to a tid file."""
        text = self.to_text()

        if path:
            pass
        elif directory and Path(directory).is_dir():
            path = os.path.join(directory, self.get_tid_file_name(self.fields["title"]))
        else:
            logging.error("Path could not be determined.")
            return

        if "type" in self.fields and self.fields["type"] != "text/vnd.tiddlywiki":
            text_parts = text.split("\n\n", 1)
            if len(text_parts) == 2:
                real_text = text_parts[1]
            else:
                real_text = ""

            with open(f"{path}.meta", mode="w+") as f:
                f.write(text_parts[0])
            with open(f"{path}", mode="w+") as f:
                f.write(real_text)
        else:
            with open(f"{path}.tid", mode="w+") as f:
                f.write(text)


class TiddlerList(list[Tiddler]):
    """
    A collection of Tiddler instances. This class exhibits the functionality of
    list and dict data types.
    """
    def __init__(self, tiddler_list=None, *args):
        super().__init__(*args)
        self.tiddler_index = dict()
        if tiddler_list is not None:
            self.extend(tiddler_list)

    def __str__(self):
        nt_strs = list()
        for nt in self:
            nt_strs.append(nt.__str__())
        list_str = "[\n\t" + "\n\t".join(nt_strs) + "\n]"
        return list_str

    def __repr__(self):
        representation_string = str()
        for i in self:
            representation_string += i.__repr__()
        return representation_string

    def __contains__(self, tid_title):
        return tid_title in self.tiddler_index

    @classmethod
    def from_json(cls, json_path):
        """
        Create TiddlerList from a JSON object containing a list of tiddler fields.
        :param json_path:
        :return:
        """
        tiddler_list = cls()
        with open(json_path) as f:
            json_object = json.load(f)
        for fields in json_object:
            tiddler = Tiddler.from_fields(fields)
            tiddler_list.append(tiddler)
        return tiddler_list

    def append(self, tiddler: Tiddler):
        if not isinstance(tiddler, Tiddler):
            logging.error(f"Cannot append object of type {type(tiddler)}")
            return

        # Checking for conflicts
        conflict_message = "TiddlerList object already contains Tiddler with {}: {}"
        if tiddler.title in [t.title for t in self]:
            logging.warning(conflict_message.format("title", tiddler.title))
            return
        if tiddler.uuid in [t.uuid for t in self]:
            logging.warning(conflict_message.format("uuid", tiddler["uuid"]))
            return

        # Writing
        self.tiddler_index[tiddler.title] = tiddler
        super().append(tiddler)

    def chain(self, initial_tag=""):
        """
        Chain the TiddlerList by setting `tags` and `neuro.primary` fields.
        :return:
        """
        current_tag = initial_tag
        for tiddler in self:
            tiddler.add_tag(current_tag)
            tiddler.fields["neuro.primary"] = current_tag
            current_tag = tiddler.title

    def display(self):
        print(self.__repr__())

    def extend(self, tiddler_list: list[Tiddler]):
        for tiddler in tiddler_list:
            self.append(tiddler)

    def remove(self, tid_title):
        if tid_title not in self:
            raise ValueError(f"Tiddler {tid_title} not found.")

        tiddler = self.tiddler_index[tid_title]
        del self.tiddler_index[tid_title]
        super().remove(tiddler)

    def write(self, dir_path):
        """
        Write TiddlerList to tid text files.
        :param dir_path: absolute pathname to directory
        :return:
        """
        os.makedirs(dir_path, exist_ok=True)
        for tiddler in self:
            tiddler.write()


class TiddlywikiHtml(TextHtml):
    """
    Wrapper for TiddlyWiki HTML file.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tiddler_list = TiddlerList()

    def __contains__(self, tid_title):
        return self.tiddler_list.__contains__(tid_title)

    @classmethod
    def from_html_legacy(cls, html):
        """
        For HTML files up to and including TiddlyWiki v5.1.23.
        :param html:
        :return:
        """
        if isinstance(html, str):
            with open(html) as f:
                tw_soup = Soup(f, "html.parser")
        elif isinstance(html, Soup):
            tw_soup = html
        elif bool(Soup(html, "html.parser").find()):
            tw_soup = Soup(html, "html.parser")
        else:
            raise TypeError(f"HTML type not supported: {type(html)}")

        tw = cls(html)

        # Collect tiddlers
        store_area_div = tw_soup.find(id="storeArea")
        tiddler_divs = store_area_div.find_all("div", recursive=False)
        for tiddler_div in tiddler_divs:
            tiddler = Tiddler.from_html(tiddler_div)
            tw.tiddler_list.append(tiddler)

        return tw

    @classmethod
    def from_html(cls, html):
        """
        “For HTML files starting from TiddlyWiki v5.2.0 and later.”
        :param html:
        :return:
        """
        with open(html) as f:
            tw_soup = Soup(f, "html.parser")

        tw = cls(html)

        store_area_json = tw_soup.find('script', class_='tiddlywiki-tiddler-store').text
        for fields in json.loads(store_area_json):
            tiddler = Tiddler.from_fields(fields)
            tw.tiddler_list.append(tiddler)

        return tw

    def write_to_wf(self, wf_path, **kwargs):
        """
        Write TiddlywikiHtml to WikiFolder.
        :return:
        """
        # Create WikiFolder
        wf = WikiFolder(wf_path, **kwargs)
        p = subprocess.Popen([
            "node",
            wf.tw5,
            wf_path,
            "--load",
            self.path
        ], stdout=subprocess.DEVNULL)
        p.wait()
        p.kill()


class WikiFolder:
    """
    Wrapper for WikiFolder. It operates on port 8099 by default.
    """
    def __init__(self, wf_path, tw5="tw5/tiddlywiki.js", **kwargs):
        """
        Initialize and verify WikiFolder
        :param wf_path: WikiFolder path
        :param exists: should the WikiFolder already exist
        :param tw5: the path to the tiddlywiki.js file
        :param silent: supress stdout
        :param port:
        :param host:
        :param tw_info: the path to the tiddlywiki.info file
        :param tiddlers_folder: folder with tiddlers to copy into WF
        """
        self.process: subprocess.Popen
        self.wf_path = wf_path
        self.tw5 = tw5
        self.port = kwargs.get("port", 8099)
        self.host = kwargs.get("host", "127.0.0.1")
        self.silent = kwargs.get("silent", False)
        self.readers = kwargs.get("readers", "(anon)")
        self.writers = kwargs.get("writers", "(anon)")
        if os.path.exists(wf_path):
            self.validate()
        else:
            if os.path.isdir(wf_path):
                raise FileExistsError
            self.create(**kwargs)

    def create(self, tiddlers_folder=None, **kwargs):
        """
        Create a new WikiFolder.
        """
        os.makedirs(self.wf_path)

        if "tw_info" in kwargs:
            tw_info = kwargs.get("tw_info")
        else:
            tw_info = internal_utils.get_path("templates") / "tiddlywiki.info"
        shutil.copy(tw_info, f"{self.wf_path}/tiddlywiki.info")

        if tiddlers_folder:
            shutil.copytree(tiddlers_folder, f"{self.wf_path}/tiddlers")
        else:
            os.makedirs(f"{self.wf_path}/tiddlers")

    def start(self):
        if self.silent:
            params = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL
            }
        else:
            params = dict()

        self.process = subprocess.Popen([
            "node",
            self.tw5,
            self.wf_path,
            "--listen",
            f"port={self.port}",
            f"host={self.host}",
            f"readers={self.readers}",
            f"writers={self.writers}"
        ], **params)

        network_utils.wait_for_socket(self.host, self.port)

        return self.process

    def validate(self):
        """
        Validate WikiFolder structure.
        """
        tw_info = f"{self.wf_path}/tiddlywiki.info"
        tiddlers_folder = f"{self.wf_path}/tiddlers"
        if not os.path.isdir(self.wf_path):
            raise exceptions.FileNotWiki(f"Not a directory: {self.wf_path}")
        if not os.path.isdir(tiddlers_folder):
            raise exceptions.FileNotWiki(f"No directory found: {tiddlers_folder}")

        if not os.path.isfile(tw_info):
            raise exceptions.FileNotWiki("No tiddlywiki.info file found.")
        with open(tw_info) as f:
            try:
                json.load(f)
            except ValueError:
                raise exceptions.FileNotWiki("File tiddlywiki.info could not be parsed as JSON.")
        return True
