"""
Unit tests of the module neuro.core.deep
"""

import os

from ..helper import get_test_file


class TestDir:
    def test_get_children(self):
        from neuro.core.deep import Dir
        dir_path = get_test_file("input/dirs/dir")
        dir_object = Dir(dir_path)
        files = dir_object.get_children(mode="file")
        assert len(files) == 4
        assert all([os.path.isfile(file) for file in files])

        dirs = dir_object.get_children(mode="dir")
        assert len(dirs) == 1
        assert all([os.path.isdir(d) for d in dirs])

    def test_get_all_paths(self):
        from neuro.core.deep import Dir
        dir_path = get_test_file("input/dirs/dir")
        dir_object = Dir(dir_path)
        files = dir_object.get_all_paths(mode="file")
        assert len(files) == 9

        all_paths = dir_object.get_all_paths(mode="def")
        assert len(all_paths) == 11


class TestFile:
    def test_mime(self):
        from neuro.core.deep import File
        text_path = get_test_file("input/files/text.txt")
        text_file = File(text_path)
        assert str(text_file.mime) == "text/plain"
        assert text_file.mime.major == "text"
        assert text_file.mime.minor == "plain"


class TestMoment:
    def test_from_string(self):
        from neuro.core.deep import Moment
        dt = Moment.from_string("26 July 2021", "%d %B %Y")
        assert int(dt.unix) == 1627257600


class TestSymlink:
    def test_symlink(self):
        from neuro.core.deep import Symlink
        target_path = get_test_file("input/dirs/dir")
        link_path = get_test_file("link", exists=False)
        os.symlink(target_path, link_path)
        assert os.path.islink(link_path)

        symlink = Symlink(link_path)
        assert symlink.target == target_path

        dir2 = target_path + "2"
        symlink.update_target(dir2)
        assert symlink.target == dir2

        symlink.delete()
        assert not os.path.islink(link_path)
