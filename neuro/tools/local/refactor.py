"""
Refactor local directories and update the wiki accordingly.
"""

import logging
from tqdm import tqdm

from neuro.core.deep import Dir
from neuro.core.files.text import Text


def update_tiddlers(src_path, dst_path, tiddlers_path):
	"""
	:param src_path:
	:param dst_path:
	:param tiddlers_path:
	"""
	count = 0
	text_paths = Dir.get_files(Dir(tiddlers_path))
	for text_path in tqdm(text_paths):
		text_file = Text(text_path)
		text = text_file.get_text()
		text_file.close()
		new_text = text.replace(src_path, dst_path)
		if text != new_text:
			text_file = Text(text_path, mode="w")
			text_file.write(new_text)
			text_file.close()
			count += 1

	logging.info(f"Tiddler files updated: {count}")


def refactor_path(src_path, dst_path, tiddlers_path):
	"""
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

	# Update paths in tiddler files
	update_tiddlers(src_path, dst_path, tiddlers_path)

	# Move locally
	src_dir.move(dst_path)
