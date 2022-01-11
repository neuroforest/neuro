"""
Internal utility constants and functions.
"""

import logging
import os
import sys

import psutil


NF_DIR = os.path.expanduser("~/Projects/NeuroForest")
PORT = 8080
URL = "127.0.0.1"


def get_path(keyword):
	"""
	Get path for a keyword.
	:param keyword: string
	:return:
	"""
	keyword_index = {
		"archive": "storage/archive",
		"design": "design",
		"data": "neuro/data",
		"desktop": "desktop",
		"neuro": "neuro",
		"nf": "",
		"nw": "desktop/output/linux64/TiddlyDesktop-linux64-v0.0.14/nw",
		"plugins": "tw/plugins",
		"tests": "neuro/tests",
		"tiddlers": "storage/tiddlers",
		"tw": "tw",
		"tw-com": "tw/editions/tw5.com/tiddlers",
		"tiddlywiki.js": "tw/tiddlywiki.js",
		"tw5-plugin-core": "tw5-plugin-core/source/core",
		"tw5-plugin-front": "tw5-plugin-front/source/front"
	}

	if keyword in keyword_index:
		return NF_DIR + "/" + keyword_index[keyword]

	logging.error(f"Keyword {keyword} is not supported.")
	sys.exit()


def get_process(name, value):
	"""

	:param name: process property name
	:param value: process property value
	:return:
	"""

	process_list = list()
	process_dict = get_process_dict()
	for process in process_dict.values():
		try:
			if process.__getattribute__(name)() == value:
				process_list.append(process)
		except AttributeError:
			continue

	return process_list


def get_process_dict():
	"""
	Get the list of all running processes.
	"""
	pids = psutil.pids()
	process_dict = dict()
	for pid in pids:
		try:
			process = psutil.Process(pid)
		except psutil.NoSuchProcess:
			continue
		process_dict[pid] = process
	return process_dict


def get_tiddler_path(tid_title):
	"""
	Return the path to the tid file p
	:param tid_title:
	:return:
	"""
	tiddlers_path = get_path("tiddlers")
	tiddler_path = f"{tiddlers_path}/{tid_title}.tid"
	return tiddler_path


if __name__ == "__main__":
	print(NF_DIR)