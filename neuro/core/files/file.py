import filecmp
import itertools
import logging
import os

from neuro.core.deep import File


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
