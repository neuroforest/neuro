import filecmp
import hashlib
import subprocess


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


def are_dirs_identical(dir1, dir2):
    cmp_object = filecmp.dircmp(dir1, dir2)
    if not cmp_object.diff_files:
        return True
    else:
        return False


def fake_subprocess(returncode=0, stdout=""):
    return lambda *a, **kw: subprocess.CompletedProcess([], returncode, stdout=stdout)
