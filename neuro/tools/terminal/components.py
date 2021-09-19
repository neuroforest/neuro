"""
General terminal interaction components.
"""

from neuro.core.files.text import Text
from neuro.tools.terminal import style


def bool_prompt(question):
	"""
	Bool prompt - yes converts to True, no to False.
	:param question: question to be assessed
	:return: bool
	"""
	while True:
		text = style.get_colored(question + " (y/n)", "BASE")
		res = input(text)
		if res.lower() == "y":
			return True
		elif not res:
			continue
		else:
			return False


def bool_prompt_show(question, file_path):
	"""
	Bool prompt - yes converts to True, no to False.
	:param question: question to be assessed
	:param file_path: path of the file to show
	:return: bool
	"""
	while True:
		text = style.get_colored(question + " (y/n/s)", "BASE")
		res = input(text)
		if res.lower() == "y":
			return True
		elif res.lower() == "s":
			text = Text(file_path).get_text()
			print("\n" + text + "\n")
			continue
		elif not res:
			continue
		else:
			return False
