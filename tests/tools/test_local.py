"""
Unit tests for the package neuro.tools.local.
"""
import logging
import os
import shutil

from ..helper import get_test_file, are_dirs_identical


class TestRefactor:
    """
    Unit tests for the module neuro.tools.local.refactor.
    """
    def test_update_tiddlers(self):
        from neuro.tools.local import refactor
        input_tiddlers = get_test_file("input/tiddlers1")
        output_tiddlers = get_test_file("output/tiddlers1", exists=False)
        result_tiddlers = get_test_file("results/tiddlers1")
        shutil.copytree(input_tiddlers, output_tiddlers)
        old = "isrubgbaprugbh;43o;ronf;84\n\n$OY("
        new = "new text"
        refactor.update_tiddlers(old, new, output_tiddlers)

        # Test the output tiddler folder
        assert are_dirs_identical(output_tiddlers, result_tiddlers)

    def test_transform(self):
        from neuro.tools.local import refactor
        input_wiki_folder_path = get_test_file("input/wikifolder")
        output_wiki_folder_path = get_test_file("output/wikifolder", exists=False)
        logging.error(input_wiki_folder_path)
        os.system(f"cp -r {input_wiki_folder_path} {output_wiki_folder_path}")
        tw_html_path = get_test_file("input/tw.html")
        refactor.transform(tw_html_path, output_wiki_folder_path)
        assert os.path.isfile(output_wiki_folder_path + "/tiddlers/Test.tid")
