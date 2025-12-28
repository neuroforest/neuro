"""
Unit tests for the package neuro.tools.local.
"""
import logging
import os
import shutil

from ..helper import get_test_file, are_dirs_identical, get_path


class TestRefactor:
    """
    Unit tests for the module neuro.tools.local.refactor.
    """
    def test_update_tiddlers(self):
        from neuro.tools.local import refactor
        input_tiddlers = get_test_file("input/tiddlers/refactor")
        output_tiddlers = get_test_file("output/tiddlers-refactor", exists=False)
        result_tiddlers = get_test_file("results/tiddlers-refactor")
        shutil.copytree(input_tiddlers, output_tiddlers)
        old = "isru[bgbaprugbh;43o;ronf;84\n\n$OY("
        new = "new text"
        refactor.update_tiddlers(old, new, output_tiddlers)

        # Test the output tiddler folder
        assert are_dirs_identical(output_tiddlers, result_tiddlers)
