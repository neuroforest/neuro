"""
Refactor local directories and update the wiki accordingly.
"""
import os
import logging
from tqdm import tqdm

from neuro.core.deep import Dir

logging.basicConfig(level=logging.INFO)


def update_tiddlers(old, new, tiddlers_path):
	"""
	:param old:
	:param new:
	:param tiddlers_path:
	"""
	# Perform full-text search
	command = f"grep -rnw {tiddlers_path} -e '{old}'"
	fts_result = os.popen(command).read()
	fts_lines = fts_result.split("\n")[:-1]

	# Perform full-text replace in affected files
	for fts_line in tqdm(fts_lines):
		tiddler_path = tuple(fts_line.split(":", 1))[0]
		with open(tiddler_path) as f:
			text = f.read()
		new_text = text.replace(old, new)
		with open(tiddler_path, "w") as f:
			f.write(new_text)

	logging.info(f"{len(fts_lines)} tiddlers affected")


def refactor_path(src_path, dst_path, tiddlers_path):
	"""
	Refactor a local path both in the file system and in NeuroStorage.

	:param src_path:
	:param dst_path:
	:param tiddlers_path:
	"""
	# Determine if the path given is valid
	try:
		src_dir = Dir(src_path)
	except FileNotFoundError:
		logging.error(f"Not a directory: {src_path}")
		return

	# Full text update in the wiki
	update_tiddlers(src_path, dst_path, tiddlers_path)

	# Move locally
	src_dir.move(dst_path)
