import filecmp
import hashlib
import subprocess
from contextlib import contextmanager


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


class Recorder:
    """Simple call recorder for monkeypatching functions."""
    def __init__(self, return_value=None):
        self.calls = []
        self.return_value = return_value

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.return_value

    @property
    def call_count(self):
        return len(self.calls)

    @property
    def last_args(self):
        return self.calls[-1][0] if self.calls else None

    @property
    def last_kwargs(self):
        return self.calls[-1][1] if self.calls else None

    def called_with_arg(self, arg):
        return any(arg in a for a, _ in self.calls)


class SubprocessResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class FakeContext:
    """Minimal invoke Context stand-in."""
    pass


@contextmanager
def noop_step(message):
    yield
