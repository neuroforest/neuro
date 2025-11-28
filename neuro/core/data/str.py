"""
String methods.
"""
import logging
import os
import uuid


class Uuid:
    @staticmethod
    def is_valid_uuid_v4(uuid_string):
        """
        Checks if a string is a valid Version 4 UUID.
        """
        try:
            uuid_obj = uuid.UUID(uuid_string)
            return uuid_obj.version == 4
        except ValueError:
            return False


class Path:
    def __init__(self, path):
        self.path = path

    def get_name(self, mode="full"):
        name = PathInfo.get_name(self.path)
        if mode == "pure":
            return name.split(".", 1)[0]
        elif mode == "full":
            return name
        else:
            logging.error(f"Mode {mode} is not supported.")
            return None

    def is_path(self):
        res_dir = os.path.isdir(self.path)
        res_file = os.path.isfile(self.path)
        return res_dir or res_file

    def resolve_symlinks(self):
        resolved = os.path.realpath(self.path)
        self.path = resolved
        return self.path


class PathInfo:
    @staticmethod
    def get_name(path):
        """
        From a path obtains the file/dir name and returns it as a sting.
        :param path:
        :return: file/dir name as a string
        :rtype: str
        """
        if path == "/":
            return path
        else:
            name = path.split("/")[-1]
            return name


class String:
    @staticmethod
    def get_readable_size(size, decimal_places=1):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                break
            size /= 1024.0
        return f"{size:.{decimal_places}f}{unit}"
