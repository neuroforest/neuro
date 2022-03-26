"""
The deepest objects upon which the platform relies.
"""

import datetime
import glob
import logging
import math
import os
import pathlib
import shutil
import time
import uuid

import magic

from neuro.core.data.dict import DictUtils
from neuro.utils import oop_utils, time_utils


class NeuroObject:
    pass


class Moment(NeuroObject):
    def __init__(self, moment=None, form="unix"):
        """
        Initialized the Moment object and determines unix time.
        :param moment: date and time input
        :param form: form of moment input
        """
        if form == "unix":
            self.unix = moment
        elif form == "utc":
            self.unix = datetime.datetime.strptime(moment, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
        elif form == "now":
            self.unix = time.time()
        else:
            logging.error("Form not recognized.")

    def __bool__(self):
        return bool(self.unix)

    def __repr__(self):
        return datetime.datetime.fromtimestamp(self.unix).strftime(time_utils.CODE_MOMENT_SI)

    def __eq__(self, other):
        return self.unix == other.unix

    def __lt__(self, other):
        return self.unix < other.unix

    def __gt__(self, other):
        return self.unix > other.unix

    @classmethod
    def from_string(cls, datetime_string, datetime_format):
        """
        :param datetime_string:
        :param datetime_format: refer to https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
        :return:
        """
        try:
            dt = datetime.datetime.strptime(datetime_string, datetime_format)
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            unix = dt.timestamp()
        except ValueError:
            logging.error(f"Time data {datetime_string} does not match format {datetime_format}")
            return cls()

        return cls(unix)

    def to_tid_val(self):
        time_format = "%Y%m%d%H%M%S%f"
        time_str = datetime.datetime.fromtimestamp(self.unix).strftime(time_format)[:-3]
        return time_str

    def to_tw_utc(self):
        time_format = "%Y-%m-%dT%H:%M:%S.%Z"
        time_str = datetime.datetime.fromtimestamp(self.unix).strftime(time_format)
        return time_str

    def to_slv(self):
        time_format = "%d.%m.%Y %H:%M:%S"
        time_str = datetime.datetime.fromtimestamp(self.unix).strftime(time_format)
        return time_str

    def to_prog(self):
        time_format = "%Y%m%d%H%M%S"
        time_str = datetime.datetime.fromtimestamp(self.unix).strftime(time_format)
        return time_str


class GeoLocation(NeuroObject):
    def __init__(self, longitude=float(), latitude=float(), elevation=float()):
        self.longitude = longitude
        self.latitude = latitude
        self.elevation = elevation

    def __bool__(self):
        return bool(self.longitude and self.latitude)

    def __eq__(self, other):
        lat = self.latitude == other.latitude
        lon = self.longitude == other.longitude
        ele = self.elevation == other.elevation
        return all([lat, lon, ele])

    @staticmethod
    def to_dms(decimal):
        """
        DMS = degrees minutes seconds
        :param decimal: decimal degrees
        :return: DMS
        """
        mnt, sec = divmod(decimal * 3600, 60)
        deg, mnt = divmod(mnt, 60)
        return str(int(deg)) + "°" + str(int(mnt)) + "'" + str(sec) + "\""

    def from_gps_dict(self, gps_dict, key_lon="lon", key_lat="lat", key_ele="ele"):
        self.longitude = gps_dict[key_lon]
        self.latitude = gps_dict[key_lat]
        self.elevation = gps_dict[key_ele]


class MIME(NeuroObject):
    """
    MIME is the media type according to specification by Internet Assigned
    Numbers Authority (IANA) - https://tools.ietf.org/html/rfc2046
    """
    def __init__(self, mime_str):
        self.minor = str()
        self.major = str()
        self.valid = bool()
        try:
            self.major, self.minor = mime_str.split("/")
            self.valid = True
        except ValueError:
            logging.error(f"Mime string is not valid: {mime_str}")
            self.valid = False

    def __repr__(self):
        if self.valid:
            return str(self.major + "/" + self.minor)
        else:
            return super().__repr__(self)

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        if self.major != other.major:
            return False
        if self.minor == other.minor or "*" in [self.minor, other.minor]:
            return True

        return False

    def __str__(self):
        return f"{self.major}/{self.minor}"


class File(NeuroObject):
    """
    File object for collecting file data and local utilities.

    :raises FileNotFoundError:
    """
    def __new__(cls, path="", mode="r"):
        if path and not os.path.exists(path) and mode == "r":
            raise FileNotFoundError(path)
        return super().__new__(cls)

    def __init__(self, path="", **kwargs):
        self.path = path
        self.mime = str()
        self.atime, self.ctime, self.mtime = tuple(Moment(form="now") for i in range(3))
        self.inode = int()
        self.size = int()
        self.owner = str()
        self.file = None
        self.text = None
        if os.path.isfile(self.path):
            self.set_basic(**kwargs)

    def __enter__(self):
        logging.error("Enter not implemented")

    def __eq__(self, other):
        """
        Duck typing.
        """
        return all([
            self.ctime == other.ctime,
            self.mtime == other.mtime,
            self.size == other.size
        ])

    def __exit__(self, exc_type, exc_value, traceback):
        logging.error("Exit not implemented")

    def __repr__(self, **kwargs):
        return oop_utils.represent(self, **kwargs)

    def display(self, **kwargs):
        print(self.__repr__())

    def display_mtime(self):
        print("The file {} was last modified:  {}".format(self.get_name(), self.mtime))

    def get_data(self):
        """Obtain the file inode."""
        return os.stat(self.path)

    def get_extension(self):
        """
        Return file suffix (extension) including the dot.
        """
        return pathlib.Path(self.path).suffix

    def get_mime_type(self):
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(self.path)
        return MIME(file_type)

    def get_name(self, extension=True):
        if extension:
            return os.path.split(self.path)[-1]
        else:
            return os.path.splitext(self.path)[0].split("/")[-1]

    def get_size(self):
        """
        Return file size as human readable string.
        Inspired by: https://stackoverflow.com/a/14822210
        """
        if self.size == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(self.size, 1024)))
        p = math.pow(1024, i)
        s = round(self.size / p, 2)
        return "%s %s" % (s, size_name[i])

    def get_stat(self):
        stat = os.stat(self.path)
        return stat

    def get_text(self):
        with open(self.path, encoding="utf-8") as f:
            try:
                text = f.read()
            except UnicodeDecodeError:
                logging.error(f"Could not decode file {self.path}")
                return None
        return text

    def get_title(self):
        return "file" + str(self.inode)

    def remove(self):
        os.remove(self.path)

    def set_basic(self, **kwargs):
        """
        Collecting file data.
        :return:
        """
        file_stat = self.get_stat()
        defaults = {
            "mime": self.get_mime_type(),
            "atime": Moment(moment=file_stat.st_atime, form="unix"),
            "ctime": Moment(moment=file_stat.st_ctime, form="unix"),
            "mtime": Moment(moment=file_stat.st_mtime, form="unix"),
            "inode": file_stat.st_ino,
            "size": file_stat.st_size,
        }
        for key, val in defaults.items():
            attr_val = kwargs.get(key, val)
            self.__setattr__(key, attr_val)


class Dir(File):
    def __init__(self, dir_path, **kwargs):
        super().__init__(dir_path)
        self.subdirs = list()
        self.subfiles = list()
        self.files = list()
        self.collect(**kwargs)

    def __repr__(self, **kwargs):
        return oop_utils.represent(self, **kwargs)

    def collect(self, **kwargs):
        """
        Collecting directory data.
        :return:
        """
        file_stat = self.get_stat()
        defaults = {
            "atime": Moment(moment=file_stat.st_atime, form="unix"),
            "ctime": Moment(moment=file_stat.st_ctime, form="unix"),
            "mtime": Moment(moment=file_stat.st_mtime, form="unix"),
            "inode": file_stat.st_ino,
            "size": file_stat.st_size
        }
        for key in defaults:
            attr_val = kwargs.get(key, defaults[key])
            self.__setattr__(key, attr_val)

    def display(self, **kwargs):
        print(self.__repr__())

    def get_all_paths(self, file_ext=None, mode="def"):
        """
        Recursively collects the paths of all the files and folders inside
        the directory given.
        :param file_ext: dot prefixed file extension
        :param mode: "def", "file", "dir" or "sym"
        :return:
            - (dir_paths, file_list) as a tuple:
                - dir_paths: list of the directory paths for all the directories
                    inside a given directory
                - file_list: list of the file paths of all the files inside a
                    given directory
            - False, if fetching failed
        """
        # Checking if directory is empty.
        if self.is_empty():
            logging.error("Directory is empty.")
            return False

        # Collecting paths.
        dir_paths = list()
        file_paths = list()
        for root, dirs, files in os.walk(self.path):
            dir_list = [root + "/" + direct for direct in dirs]
            file_list = [root + "/" + file for file in files]
            dir_paths.extend(dir_list)
            file_paths.extend(file_list)

        if file_ext:
            logging.error("Filtering by file_ext is not supported")
        elif mode == "sym":
            symlinks = list()
            for file_path in file_paths:
                if os.path.islink(file_path):
                    symlinks.append(file_path)
            for dir_path in dir_paths:
                if os.path.islink(dir_path):
                    symlinks.append(dir_path)
            return symlinks
        elif mode == "file":
            return file_paths
        elif mode == "dir":
            return dir_paths
        else:
            return dir_paths + file_paths

    def get_children(self, mode="def"):
        """
        Return the absolute pathnames of all file node children according to
        criteria given.

        :param mode: "def", "file" or "dir"
        :return: list of absolute pathnames
        """
        children = glob.glob(f"{self.path}/*")
        if mode == "def":
            return children
        elif mode == "file":
            return [child for child in children if os.path.isfile(child)]
        elif mode == "dir":
            return [child for child in children if os.path.isdir(child)]
        else:
            logging.error(f"Mode {mode} is not supported.")
            return []

    def get_item_number(self, file_ext):
        return len(os.listdir(self.path))

    def get_latest_file(self, mode="def", recursive=True, mime_major=None):
        """
        Finds and returns the path of the file that was created the last
        in the folder.

        :param mode: method mode
        :param recursive:
        :param mime_major:
        :return:
            - if mode is 'def', full file path is returned
            - if mode is 'name', only file name string is returned
        """
        if recursive:
            file_paths = self.get_all_paths(mode="file")
        else:
            file_paths = self.get_children(mode="file")
        latest_file = max(file_paths, key=os.path.getmtime)

        if mime_major and latest_file:
            file_mime_major = magic.Magic(mime=True).from_file(latest_file).split("/")[0]
            if file_mime_major == mime_major:
                return latest_file

        if mode == "name":
            file_name = latest_file.split("/")[-1]
            return file_name
        else:
            return latest_file

    def get_stat(self):
        stat = os.stat(self.path)
        return stat

    def get_title(self):
        return "dir" + str(self.inode)

    def get_files(self, file_ext=None):
        file_paths = self.get_all_paths(mode="file", file_ext=file_ext)
        return file_paths

    def is_empty(self):
        """
        Checks if any data is stored inside a given directory.

        :return:
            - True, if dir path is empty or doesn't exist
            - False, if dir path is not empty
        """
        for root, dirs, files in os.walk(self.path):
            if files:
                return False

        return True

    def move(self, dst_path, force=False):
        if not os.path.isdir(dst_path) or force:
            shutil.move(self.path, dst_path)
        else:
            logging.warning(f"Dircetory {dst_path} already exists, use 'force' to overwrite")


class Symlink(NeuroObject):
    def __init__(self, symlink_path):
        self.path = symlink_path
        self.target = os.path.realpath(symlink_path)

    def delete(self):
        """
        Remove symlink but preserve target.
        """
        os.unlink(self.path)

    def update_target(self, new_target):
        """
        Update symlink to point to a new target.
        """
        self.delete()
        os.symlink(new_target, self.path)
        self.target = new_target


class NeuroNode(NeuroObject):
    """
    NeuroNode represents the specific position of a node inside primary tree
    and the NeuroForest platform.
    """
    def __init__(self, **kwargs):
        # Setup the data infrastructure.
        self.uuid = kwargs.get("uuid", str())
        self.set_id()
        self.edges = kwargs.get("edges", Edges())

    def __eq__(self, other):
        if isinstance(other, NeuroNode):
            return other.uuid == self.uuid
        else:
            return NotImplemented

    def __getitem__(self, item):
        return getattr(self, item)

    def __hash__(self):
        return int(self.uuid, 16)

    def __repr__(self):
        """
        Display the node data in the terminal.
        :return:
        """
        attrs_keys = oop_utils.get_attr_keys(self, modes={"no_func", "simple"})

        attrs = {k: self[k] for k in attrs_keys}
        return DictUtils.represent(attrs, display=False)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __str__(self):
        return str(self.uuid)

    def set_id(self):
        """
        Obtains and configures the neuro id. Currently using the uuid v1.
        """
        if not self.uuid:
            self.uuid = uuid.uuid4().hex

    def to_dict(self):
        attrs = oop_utils.get_attr_keys(self)
        attr_dict = dict()
        for attr_name in attrs:
            attr_dict[attr_name] = getattr(self, attr_name)
        return attr_dict

    def get_methods(self):
        method_dict = dict()
        attr_dict = self.to_dict()
        for attr_name in attr_dict:
            type_name = type(attr_dict[attr_name]).__name__
            if type_name == "method":
                method_dict[attr_name] = attr_dict[attr_name]
        return method_dict

    def display(self):
        print(self.__repr__())


class Edge(NeuroObject):
    def __init__(self, source, target):
        super().__init__()
        self.weight = 0
        self.source = source
        self.target = target

    def __str__(self):
        string = "{} --> {}"
        return string.format(
            self.source.name,
            self.target.name)

    def apply_to(self, neuro_nodes):
        for neuro_node in neuro_nodes:
            edges = neuro_node.edges
            if self not in edges:
                edges.append(self)


class Edges(list):
    """
    NeuroEdges is an array of object of type NeuroEdgs with some special
    functionality.
    """
    def __init__(self, edges=None):
        self.edges = edges
        if self.are_edges_ok():
            super().__init__(edges)
        else:
            super().__init__()

    def __str__(self):
        collected_string = str()
        for edge in self:
            collected_string += edge.__str__() + "\n"
        return collected_string

    def are_edges_ok(self):
        """
        Checks if edges given at construction are valid.
        :return:
        """
        try:
            it = iter(self.edges)
            for i in it:
                if not isinstance(i, Edge):
                    return False
            return True
        except TypeError:
            return False

    def get_edge(self, edge_type):
        """
        Returns an edge
        :param edge_type:
        :return:
        :rtype:
        """
        for edge in self:
            print(edge.type)
            if edge.type == edge_type:
                return edge

    def get_primary(self):
        return self.get_edge("primary")
