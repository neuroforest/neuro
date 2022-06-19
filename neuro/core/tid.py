"""
Object associated with TiddlyWiki5 and related data.
"""
import json
import logging
import os
import re
import subprocess

from bs4 import BeautifulSoup as Soup
from bs4.element import Tag

from neuro.core.deep import NeuroNode
from neuro.core.files.text import TextHtml
from neuro.utils import oop_utils, exceptions, internal_utils, network_utils


class NeuroTid(NeuroNode):
    """
    NeuroTid is a Python representation of tiddler, that is an element of
    NeuroForest platform.
    There are 3 fundamental object properties:
        - uuid - inherited from NeuroNode
        - title - tiddler title, also serves as identifier
        - fields - a dictionary of all fields, some with special handling:
            - tags - list
    """
    def __init__(self, tid_title="", fields=None, **kwargs):
        super().__init__(**kwargs)
        self.title = tid_title
        if fields and isinstance(fields, dict):
            self.fields = fields
        else:
            self.fields = dict()

    def __bool__(self):
        return bool(self.title)

    def __delitem__(self, key):
        if key in self:
            del self.fields[key]

    def __getitem__(self, key):
        if key in ["title", "edges", "uuid", "fields"]:
            return super().__getitem__(key)
        else:
            return self.fields[key]

    def __contains__(self, key):
        d = {
            **self.fields,
            "edges": self.edges,
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
        return f"<NeuroTid title=\"{self.title}\">"

    def add_fields(self, fields, overwrite=False):
        """
        Add fields to neuro_tid.

        Similar to NeuroBit.extend_fields.

        :param fields: dict
        :param overwrite: override existing fields
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
                logging.error("Incorrect data type of field `tags`, should be list.")
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
        elif bool(Soup(html, "html.parser").find()):
            soup = Soup(html, features="lxml")
            div_element = soup.find("div")
        else:
            raise TypeError(f"HTML type not supported: {type(html)}")

        tid_fields = div_element.attrs
        tid_fields["text"] = div_element.text
        try:
            tid_title = tid_fields["title"]
            neuro_tid = cls(tid_title, tid_fields)
            return neuro_tid
        except KeyError:
            logging.error(f"No title in HTML: {html}")
            return cls()

    @classmethod
    def from_tiddler(cls, tiddler):
        """
        Populate NeuroTid properties from a tiddler.

        :param tiddler:
        :param kwargs:
            - ignore: list of fields to ignore when importing from tiddler
              - override: override NeuroTid properties
        :return:
        """
        try:
            tid_title = tiddler["title"]
        except KeyError:
            raise exceptions.MissingTitle()
        neuro_tid = cls(tid_title, tiddler)
        return neuro_tid

    @staticmethod
    def get_tid_file_name(tid_title):
        """
        Replace special characters in file, for example: :,/,\
        """
        tid_file_name = tid_title
        tid_file_name = re.sub(r"\/|\\", "_", tid_file_name)
        tid_file_name = re.sub(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])$", "_$1_", tid_file_name, flags=re.IGNORECASE)
        tid_file_name = re.sub(r"^ +", "_", tid_file_name)
        tid_file_name = re.sub(r"[\x00-\x1f\x80-\x9f]", "_", tid_file_name)
        tid_file_name = re.sub(r"<|>|~|\:|\"|\||\?|\*|\^", "_", tid_file_name)

        # Truncate
        if len(tid_file_name) > 200:
            tid_file_name = tid_file_name[:200]

        return tid_file_name

    @staticmethod
    def to_text(fields):
        """
        Determine tid file text.
        """
        if "text" in fields:
            tid_text = fields["text"]
        else:
            tid_text = None

        text = str()
        for field in sorted(fields):
            if field in fields and field != "text":
                text += f"{field}: {fields[field]}\n"

        if tid_text:
            text += f"\n{tid_text}"
        else:
            # Remove redundant \n
            text = text[:-1]

        return text

    def to_tiddler(self, only_true=True):
        # Extracting data.
        tiddler_keys = oop_utils.get_attr_keys(self, modes={"simple", "no_func"})
        tiddler = dict()
        for key in tiddler_keys:
            val = self[key]

            if isinstance(val, set):
                val = list(val)

            tiddler[key] = val

        # Removing false values.
        if only_true:
            tiddler = {key: val for key, val in tiddler.items() if val}

        return tiddler

    def write(self, fields=None, directory="", path=""):
        """Write to tid text file."""
        if not fields:
            fields = self.fields
        else:
            fields = {**self.fields, **fields}

        text = self.to_text(fields)

        # Determine path
        if directory:
            path = os.path.join(directory, self.get_tid_file_name(fields["title"]))
        else:
            if not path:
                logging.error(f"No directory given for writing: {fields['title']}")
                return

        with open(path, "w+", encoding="utf-8") as f:
            f.write(text)


class NeuroTids(list):
    """
    A collection of NeuroTid instances. This class exhibits functionality of
    list and dict data types.
    """
    def __init__(self, neuro_tids=None, *args):
        super().__init__(*args)
        self.object_index = dict()
        if neuro_tids:
            self.extend(neuro_tids)

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
        return tid_title in self.object_index

    def append(self, neuro_tid: NeuroTid):
        if not isinstance(neuro_tid, NeuroTid):
            logging.error(f"Cannot append object of type {type(neuro_tid)}")
            return

        # Checking for conflicts.
        conflict_message = "NeuroTids object already contains NeuroTid with {}: {}"
        if neuro_tid.title in [nt.title for nt in self]:
            logging.warning(conflict_message.format("title", neuro_tid.title))
            return
        if neuro_tid["uuid"] in [nt["uuid"] for nt in self]:
            logging.warning(conflict_message.format("uuid", neuro_tid["uuid"]))
            return

        # Writing.
        super().append(neuro_tid)
        self.object_index[neuro_tid.title] = neuro_tid

    def chain(self, initial_tag=""):
        """
        Chain the NeuroTids by setting `tags` and `neuro.primary` fields.
        :return:
        """
        current_tag = initial_tag
        for neuro_tid in self:
            neuro_tid.add_tag(current_tag)
            neuro_tid.fields["neuro.primary"] = current_tag
            current_tag = neuro_tid.title

    def display(self):
        print(self.__repr__())

    def extend(self, neuro_tid_list):
        for neuro_tid in neuro_tid_list:
            self.append(neuro_tid)

    def remove(self, tid_title):
        if tid_title not in self:
            raise ValueError(f"Tiddler {tid_title} not found.")

        neuro_tid = self.object_index[tid_title]
        super().remove(neuro_tid)
        del self.object_index[tid_title]

    def write_dir(self, dir_path):
        """
        Write NeuroTids to tid text files.
        :param dir_path: absolute pathname to directory
        :return:
        """
        os.makedirs(dir_path, exist_ok=True)
        for neuro_tid in self:
            tid_file_title = neuro_tid.get_tid_file_name(neuro_tid.title)
            tid_text = neuro_tid.to_text(neuro_tid.fields)
            if "type" in neuro_tid.fields:
                text_parts = tid_text.split("\n\n", 1)
                if len(text_parts) == 2:
                    real_text = text_parts[1]
                else:
                    real_text = ""

                with open(f"{dir_path}/{tid_file_title}.meta", mode="w+") as f:
                    f.write(text_parts[0])
                with open(f"{dir_path}/{tid_file_title}", mode="w+") as f:
                    f.write(real_text)
            else:
                with open(f"{dir_path}/{tid_file_title}.tid", mode="w+") as f:
                    f.write(tid_text)


class NeuroTW(TextHtml):
    """
    Wrapper for TiddlyWiki HTML file.
    """
    def __init__(self):
        super().__init__()
        self.neuro_tids = NeuroTids()

    def __contains__(self, tid_title):
        return self.neuro_tids.__contains__(tid_title)

    @classmethod
    def from_html(cls, html):
        if isinstance(html, str):
            with open(html) as f:
                tw_soup = Soup(f, "html.parser")
        elif isinstance(html, Soup):
            tw_soup = html
        elif bool(Soup(html, "html.parser").find()):
            tw_soup = Soup(html, "html.parser")
        else:
            raise TypeError(f"HTML type not supported: {type(html)}")

        neuro_tw = cls()

        # Collect tiddlers
        store_area_div = tw_soup.find(id="storeArea")
        tiddler_divs = store_area_div.find_all("div", recursive=False)
        for tiddler_div in tiddler_divs:
            neuro_tid = NeuroTid.from_html(tiddler_div)
            neuro_tw.neuro_tids.append(neuro_tid)

        return neuro_tw


class NeuroWF:
    """
    Wrapper for WikiFolder.
    """
    def __init__(self, wf_path, exists=True):
        """
        Initialize and verify WikiFolder
        :param wf_path: WikiFolder path
        :param exists: should the WikiFolder already exist
        """
        self.process: subprocess.Popen
        self.wf_path = wf_path
        if exists:
            tiddlywiki_info = f"{wf_path}/tiddlywiki.info"
            tiddlers = f"{wf_path}/tiddlers"
            if not os.path.isdir(wf_path):
                raise exceptions.FileNotWiki(f"Not a directory: {wf_path}")
            if not os.path.isdir(tiddlers):
                raise exceptions.FileNotWiki(f"No directory found: {tiddlers}")

            if not os.path.isfile(tiddlywiki_info):
                raise exceptions.FileNotWiki("No tiddlywiki.info file found.")
            with open(tiddlywiki_info) as f:
                try:
                    json.load(f)
                except ValueError:
                    raise exceptions.FileNotWiki("File tiddlywiki.info could not be parsed as JSON.")
        else:
            if os.path.isdir(wf_path):
                raise FileExistsError
            self.create()

    def create(self, **kwargs):
        """
        Create new WikiFolder.
        """
        if "tw_info_template" in kwargs:
            tw_info_template = kwargs.get("tw_info_template")
        else:
            tw_info_template = internal_utils.get_path("templates") + "/tiddlywiki.info"
        with open(tw_info_template) as f:
            tw_info = json.load(f)
        for key in kwargs:
            tw_info[key] = kwargs.get(key)

        os.makedirs(self.wf_path)
        tw_info_path = self.wf_path + "/tiddlywiki.info"
        with open(tw_info_path, "w+") as f:
            json.dump(tw_info, f, indent=4)

    def open(self, tw5="tw5/tiddlywiki.js", port=8099):
        self.process = subprocess.Popen([
            "node",
            tw5,
            self.wf_path,
            "--listen",
            f"port={port}"
        ], stdout=subprocess.DEVNULL, close_fds=True)

        network_utils.wait_for_socket("127.0.0.1", port)

    def close(self):
        self.process.kill()
