"""
Transferring text file data into NeuroForest.
"""

import csv
import io
import json
import logging
import operator
import os
import re

from neuro.core.data.dict import DictUtils
from neuro.core import File
from neuro.utils import exceptions


class Text(File):
    def __init__(self, path="", mode="r", **kwargs):
        self.mode = mode
        super().__init__(path, **kwargs)

        self.text = str()
        self.file: io.TextIOWrapper
        self.file_objects = list()
        if path and (os.path.isfile(path) or mode != "r"):
            self.set()

    def __enter__(self):
        try:
            self.file = open(self.path, self.mode)
            return self
        except Exception as e:
            print(f"Error opening file: {e}")
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        for file_object in self.file_objects:
            file_object.close()

    def close(self):
        if isinstance(self.file, io.TextIOWrapper):
            self.file.close()

    def set(self):
        self.file = open(self.path, self.mode)

    def write(self, text):
        if isinstance(self.file, io.TextIOWrapper):
            self.file.write(text)

    def get_file_object(self, mode=""):
        if not mode:
            mode = self.mode

        file_object = open(self.path, mode)
        self.file_objects.append(file_object)
        return file_object

    def get_row_nr(self):
        """
        Return row number
        """
        return len(self.get_rows())

    def get_rows(self):
        """
        Return list of rows
        """
        text = self.get_text()
        if text:
            return text.split("\n")
        else:
            return []

    def get_text(self):
        """
        Return the string of text.
        """
        if isinstance(self.file, io.TextIOWrapper):
            try:
                return self.file.read()
            except UnicodeDecodeError:
                logging.error(f"File {self.path} cannot be read")
                return ""
        else:
            return ""


class TextCsv(Text):
    def __init__(self, path="", mode="r"):
        self.header = list()
        super().__init__(path, mode)

    def get_column(self, header):
        header_list = self.get_header()
        index = header_list.index(header)

        column = list()
        for row in self.get_rows():
            column.append(row[index])

        return column

    def get_header(self):
        """
        Return header as a list.
        :return:
        :rtype: list
        """
        if not self.header:
            file_object = self.get_file_object()
            reader = csv.reader(file_object)
            self.header = next(reader)
            file_object.close()

        return self.header

    def get_reader(self):
        """
        Get csv reader.
        :return:
        :rtype: csv.reader
        """
        file_object = self.get_file_object("r")
        reader = csv.reader(file_object)
        return reader

    def get_rows(self, header_rows=1):
        """
        Get only data rows by excluding the header rows.
        :param header_rows:
        :return:
        """
        reader = self.get_reader()
        for i in range(header_rows):
            next(reader)
        return reader

    def get_writer(self):
        """
        Get csv reader.
        :return:
        :rtype: csv.reader
        """
        file_object = self.get_file_object("w+")
        writer = csv.writer(file_object)
        return writer

    def extract_headers(self, headers, output_path=""):
        """
        Extract certain headers from csv file.

        :param headers: list of headers to extract
        :param output_path: path to write extracted row
        :return:
        """
        header_list = self.get_header()
        index_list = list()
        for header in headers:
            if header not in header_list:
                raise exceptions.InvalidHeader(header)
            else:
                index = header_list.index(header)
            index_list.append(index)

        new_lol = list()
        new_lol.append(headers)
        for row in self.get_rows():
            new_row_list = list()
            for index in index_list:
                new_row_list.append(row[index])
            new_lol.append(new_row_list)

        if output_path:
            TextCsv(output_path, mode="w+").write(new_lol)
        else:
            return new_lol

    def is_identifier(self, key):
        """
        Check if a csv column has only unique values.
        :return:
        :rtype: bool
        """
        header = self.get_header()
        key_index = header.index(key)

        key_list = list()
        for row in self.get_rows():
            key_value = row[key_index]
            if key_value in key_list:
                logging.error(f"Double key: {key_value}")
                return False
            else:
                key_list.append(key_value)

        return True

    def set(self):
        super().set()
        try:
            self.get_header()
        except StopIteration:
            pass

    def sort_by(self, header, reverse=False):
        header_list = self.get_header()
        if header not in header_list:
            raise exceptions.InvalidHeader
        else:
            index = header_list.index(header)
        lol = self.get_rows()

        # Convert to float if possible
        float_lol = list()
        for row in lol:
            new_row = list()
            for i in row:
                try:
                    i = float(i)
                except ValueError:
                    pass
                new_row.append(i)
            float_lol.append(new_row)

        sorted_rows = sorted(float_lol, key=operator.itemgetter(index), reverse=reverse)
        sorted_rows.insert(0, header_list)
        self.write(sorted_rows)

    def to_json(self, header_key=None, json_path=None, mode="local"):
        """
        Convert csv to json by using specific column for keys.
        :param header_key: the column of CSV that is used as identifier
        :param json_path:
        :param mode: "local" or "dict"
        :return:
        """
        self.get_header()

        if not header_key:
            key_index = None
        elif header_key in self.header and self.is_identifier(header_key):
            key_index = self.header.index(header_key)
        elif not self.is_identifier(header_key):
            return exceptions.InternalError(f"Header {header_key} is not an identifier.")
        else:
            logging.error(f"Key: {header_key}, Header: {self.header}, CSV: {self.path}")
            raise ValueError

        data_dict = dict()

        count = 0
        for row in self.get_rows():
            if key_index is None:
                key_value = count
            else:
                key_value = row[key_index]
            row_dict = dict()
            for i in range(len(self.header)):
                row_dict[self.header[i]] = row[i]

            data_dict[key_value] = row_dict
            count += 1

        if mode == "local":
            with TextJson(json_path, "w") as t:
                t.dump(data_dict)
                return dict()
        elif mode == "dict":
            return data_dict
        else:
            exceptions.InternalError(f"Mode '{mode}' is not supported.")
            return dict()

    def write(self, lol):
        writer = self.get_writer()
        writer.writerows(lol)


class TextHtml(Text):
    pass


class TextXml(Text):
    pass


class TextJson(Text):
    def __init__(self, path="", mode="r", **kwargs):
        self.dict = dict()
        super().__init__(path, mode=mode, **kwargs)

    def set(self):
        super().set()
        try:
            self.dict = json.load(self.file)
        except io.UnsupportedOperation:
            return

    def dump(self, data_dict=None):
        if not data_dict:
            data_dict = self.dict
        json.dump(data_dict, self.file)

    def insert_layer(self, layer, output_path=""):
        """
        Insert a layer into the JSON tree structure.
        :param layer: string
        :param output_path:
        :return:
        """
        if not output_path:
            output_path = self.path
        self.set()
        updated_json_data = dict()

        for key, value in self.dict.items():
            updated_json_data[key] = {layer: value}

        with open(output_path, "w+", encoding="utf-8") as f:
            json.dump(updated_json_data, f)

    @staticmethod
    def merge_files(json_path_list, merged_path):
        """
        Merge json files with unique keys.
        :param json_path_list:
        :param merged_path:
        :return:
        """
        json_dict_list = list()
        for json_path in json_path_list:
            with open(json_path, encoding="utf-8") as f:
                json_dict = json.load(f)
                json_dict_list.append(json_dict)
        merged_data = DictUtils.merge_dicts(json_dict_list)

        with open(merged_path, "w+", encoding="utf-8") as f:
            json.dump(merged_data, f)

    def count_subchildren(self):
        self.set()
        subchildren_count = dict()
        for child in self.dict:
            subchildren = self.dict[child].keys()
            for subchild in subchildren:
                if subchild in subchildren_count:
                    subchildren_count[subchild] += 1
                else:
                    subchildren_count[subchild] = 1

        return subchildren_count


class TextTid(Text):
    def __init__(self, path):
        super().__init__(path)
        self.fields = self.to_fields()

    def to_fields(self):
        fields = dict()
        rows = self.get_rows()
        pattern = re.compile(r"^[a-z0-9\-._]+:\s.*", re.M)
        for i in range(len(rows)):
            row = rows[i]
            matches = re.match(pattern, row)
            if matches:
                name, value = row.split(": ", 1)
                fields[name] = value
            else:
                text = "\n".join(rows[i:]).strip()
                fields["text"] = text
                break

        return fields
