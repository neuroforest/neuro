"""
Unit tests of the module neuro.core.files.file
"""


class TestFileUtils:
    def test_are_identical(self, test_file):
        from neuro.core.file.file import FileUtils
        file_1 = test_file.get("input/files/text.txt")
        file_2 = test_file.get("input/files/text_identical.txt")
        file_3 = test_file.get("input/files/text.json")
        r = FileUtils.are_identical([file_1, file_2])
        assert r
        r = FileUtils.are_identical([file_1, file_3])
        assert not r
        r = FileUtils.are_identical([file_1, file_2, file_3])
        assert not r
        r = FileUtils.are_identical([file_1, file_2], times=True)
        assert not r
