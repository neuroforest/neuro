"""
String methods.
"""
import os
import logging


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
