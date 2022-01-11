"""
Object associated with TiddlyWiki5 and related data.
"""

import logging
import os
import re

from bs4 import BeautifulSoup as Soup
from bs4.element import Tag

from neuro.utils import oop_utils,exceptions
from neuro.core.deep import Edges,NeuroBit
from neuro.core.data.dict import DictUtils
from neuro.core.files.text import TextHtml,  TextJson


class NeuroNode(NeuroBit):
    """
    NeuroNode represents the specific position of a node inside primary tree
    and the NeuroForest platform.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.edges = kwargs.get("edges", Edges())

    def display(self, modes=None):
        """
        Display the node data in the terminal.
        :param modes: set of modes
        :return:
        """
        # Default modes.
        if not modes:
            modes = {"no_func", "simple"}

        attrs_keys = oop_utils.get_attr_keys(self, modes=modes)

        attrs = {k: self[k] for k in attrs_keys}
        DictUtils.display(attrs)


class NeuroTid(NeuroNode):
    """
    Represent the custom Tiddler implementation with some obligatory
    information:
        - tmap.id (from NeuroBit)
        - title
        - text
        - type

    Intended to be displayed.

    """
    def __init__(self, tid_title, tmap_id=None, **kwargs):
        super().__init__(uuid=tmap_id, **kwargs)
        self.fields = dict()
        self.title = tid_title
        self.text = str()

    def __str__(self):
        return f"<NeuroTid title=\"{self.title}\">"

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
        try:
            tid_title = tid_fields["title"]
        except KeyError:
            logging.error(html)

        neuro_tid = cls(tid_title)
        neuro_tid.fields = tid_fields
        neuro_tid.title = tid_title
        neuro_tid.text = div_element.text
        return neuro_tid

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
        neuro_tid = cls(tid_title)
        neuro_tid.title = tiddler["title"]
        if "text" in tiddler:
            neuro_tid.text = tiddler["text"]
        neuro_tid.fields = tiddler
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

    def index_text(self):
        if not self.text:
            logging.info("Nothing to index.")

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


class NeuroTids(list):
    """
    It a graph where every node is a NeuroTid object and they are linked together
    by usidng NeureEdges object.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.neuro_index = dict()

    def __str__(self):
        nt_strs = list()
        for nt in self:
            nt_strs.append(nt.__str__())
        list_str = "[\n\t" + "\n\t".join(nt_strs) + "\n]"
        return list_str

    def __contains__(self, tid_title):
        return tid_title in self.neuro_index

    @classmethod
    def from_json(cls, json_path):
        """
        :param json_path:
        """
        neuro_tids = cls()
        tiddlers = TextJson(json_path).dict["tiddlers"]
        for tiddler in tiddlers:
            neuro_tid = NeuroTid.from_tiddler({**tiddlers[tiddler], **{"title": tiddler}})
            neuro_tids.append(neuro_tid)

        return neuro_tids

    def append(self, neuro_tid):
        if not isinstance(neuro_tid, NeuroTid):
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
        self.neuro_index[neuro_tid.title] = neuro_tid.fields
        self.neuro_index[neuro_tid.title]["object"] = neuro_tid

    def extend(self, neuro_tid_list):
        for neuro_tid in neuro_tid_list:
            self.append(neuro_tid)

    def remove(self, tid_title):
        if tid_title not in self:
            raise ValueError(f"Tiddler {tid_title} not found.")

        index_item = self.neuro_index[tid_title]
        neuro_tid = index_item["object"]
        super().remove(neuro_tid)
        del self.neuro_index[tid_title]

    def write_dir(self, dir_path):
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
