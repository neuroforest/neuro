import filecmp
import glob
import itertools
import logging
import magic
import math
import os
import pathlib
import shutil

from neuro.core import Moment, Object
from neuro.utils import oop_utils


class MIME(Object):
    """
    MIME is the media type according to specification by Internet Assigned
    Numbers Authority (IANA) - https://tools.ietf.org/html/rfc2046
    """
    def __init__(self, mime_str):
        self.minor = str()
        self.major = str()
        self.valid = bool()
        self.mime = str()
        try:
            self.major, self.minor = mime_str.split("/")
            self.valid = True
            self.mime = f"{self.major}/{self.minor}"
        except ValueError:
            logging.error(f"Mime string is not valid: {mime_str}")
            self.valid = False

    def __repr__(self):
        if self.valid:
            return str(self.major + "/" + self.minor)
        else:
            return super().__repr__(self)

    def __eq__(self, other):
        if type(self) is type(other):
            return False
        if self.major != other.major:
            return False
        if self.minor == other.minor or "*" in [self.minor, other.minor]:
            return True

        return False

    def __str__(self):
        return f"{self.major}/{self.minor}"


class File(Object):
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
        self.atime, self.ctime, self.mtime = tuple(Moment() for i in range(3))
        self.inode = int()
        self.size = int()
        self.owner = str()
        self.file = None
        self.text = None
        self.name = os.path.basename(self.path)
        if os.path.isfile(self.path):
            self.set_basic(**kwargs)

    def __enter__(self):
        return self

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
        pass

    def __repr__(self, **kwargs):
        return oop_utils.represent(self, **kwargs)

    def display(self, **kwargs):
        print(self.__repr__())

    def display_mtime(self):
        print("The file {} was last modified:  {}".format(self.name, self.mtime))

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
        self.text = text
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
        dir_stat = self.get_stat()
        defaults = {
            "atime": Moment(moment=dir_stat.st_atime, form="unix"),
            "ctime": Moment(moment=dir_stat.st_ctime, form="unix"),
            "mtime": Moment(moment=dir_stat.st_mtime, form="unix"),
            "inode": dir_stat.st_ino,
            "size": dir_stat.st_size
        }
        for key in defaults:
            attr_val = kwargs.get(key, defaults[key])
            self.__setattr__(key, attr_val)

    def display(self, **kwargs):
        print(self.__repr__(**kwargs))

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
        sorted_file_paths = sorted(file_paths, key=lambda x: os.stat(x).st_mtime)
        latest_file = sorted_file_paths[-1]

        if mime_major and latest_file:
            file_mime_major = magic.Magic(mime=True).from_file(latest_file).split("/")[0]
            if file_mime_major == mime_major:
                return latest_file

        if mode == "name":
            file_name = latest_file.split("/")[-1]
            return file_name
        else:
            return latest_file

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


class Symlink(Object):
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


class FileInfo:
    def __init__(self, file_path):
        self.path = file_path

    def get_file_extension(self):
        """
        Returns the extension of a file (dot included).

        :return: file_ext
        :rtype: str
        """
        return os.path.splitext(self.path)[1]


class FileUtils:
    @staticmethod
    def are_identical(path_list, times=False):
        """
        Determine if the files given are identical to each other.
        :param path_list:
        :param times: check accessed, created and modified times
        :rtype: bool
        """
        combinations = list(itertools.combinations(path_list, 2))
        results = list()
        for file_path1, file_path2 in combinations:
            file1, file2 = File(file_path1), File(file_path2)
            if times:
                r = file1 == file2
            else:
                r = filecmp.cmp(file_path1, file_path2)

            results.append(r)

        return all(results)

    @staticmethod
    def get_latest(file_list, mode="created"):
        """
        Calculate and return the file from file list that was created / modified
        latest.

        :param file_list: list of file pathnames
        :param mode:
            - created
            - modified
        :return: latest pathname
        """
        if mode == "created":
            try:
                latest = max(file_list, key=os.path.getctime)
            except FileNotFoundError as e:
                logging.error(f"BROKEN: symbolic link '{e.filename}'")
                return False
        elif mode == "modified":
            latest = max(file_list, key=os.path.getmtime)
        else:
            logging.error("Function mode not supported.")
            return False

        return latest
