"""
Unit tests for the package neuro.tools.local.
"""
import shutil


class TestRefactor:
    """
    Unit tests for the module neuro.tools.local.refactor.
    """
    def test_update_tiddlers(self, test_file):
        from neuro.tools.local import refactor
        from neuro.utils.test_utils import are_dirs_identical
        input_tiddlers = test_file.get("input/tiddlers/refactor")
        output_tiddlers = test_file.path("output/tiddlers-refactor")
        result_tiddlers = test_file.get("results/tiddlers-refactor")
        shutil.copytree(input_tiddlers, output_tiddlers)
        old = "isru[bgbaprugbh;43o;ronf;84\n\n$OY("
        new = "new text"
        refactor.update_tiddlers(old, new, output_tiddlers)

        # Test the output tiddler folder
        assert are_dirs_identical(output_tiddlers, result_tiddlers)
