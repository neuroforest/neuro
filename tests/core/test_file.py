"""
Unit tests of the module neuro.core.files.file
"""

from ..helper import get_test_file


class TestFileUtils:
    def test_are_identical(self):
        from neuro.core.file.file import FileUtils
        file_1 = get_test_file("input/files/text.txt")
        file_2 = get_test_file("input/files/text_identical.txt")
        file_3 = get_test_file("input/files/text.json")
        r = FileUtils.are_identical([file_1, file_2])
        assert r
        r = FileUtils.are_identical([file_1, file_3])
        assert not r
        r = FileUtils.are_identical([file_1, file_2, file_3])
        assert not r
        r = FileUtils.are_identical([file_1, file_2], times=True)
        assert not r
