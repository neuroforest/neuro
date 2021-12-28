"""
Helper function and classes used by various tests.
"""

import glob
import hashlib
import io
import logging
import os
import sys


def get_test_file(file_name, exists=True, multi=False):
	"""
	Get a test file according to glob file path expansion.
	:param file_name:
	:param exists: does file have to exist
	:param multi:
	:return:
	"""
	test_data_dir = os.path.abspath("data/test")  # IMPORTANT: must be in dir
	if exists:
		file_paths = sorted(glob.glob(f"{test_data_dir}/*{file_name}*"))
		if len(file_paths) == 1:
			return file_paths[0]
		elif not file_paths:
			logging.error(f"Test data file not found: {file_name}")
			logging.error(f"Test data dir: {test_data_dir}")
			return False
		else:
			if not multi:
				logging.error(f"Test data file name not specific enough, found {len(file_paths)}")
				return False
			else:
				return file_paths
	else:
		return f"{test_data_dir}/{file_name}"


def get_hash(string):
	"""
	Get a hash from a string.
	:param string:
	:return:
	"""
	m = hashlib.sha1()
	m.update(bytes(string, encoding="utf-8"))
	digest = m.hexdigest()
	return digest


class Capturing(list):
	def __enter__(self):
		self._stdout = sys.stdout
		sys.stdout = self._stringio = io.StringIO()
		return self

	def __exit__(self, *args):
		self.extend(self._stringio.getvalue().splitlines())
		del self._stringio    # free up some memory
		sys.stdout = self._stdout
