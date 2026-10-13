import importlib.metadata
import pathlib

__name__ = "neuro"


def _version() -> str:
    # One literal, the repo's VERSION file (PLAN-2026-321): pyproject.toml reads it
    # as `dynamic`, so an installed wheel carries it in its metadata. A checkout —
    # bare on sys.path, or an editable install whose metadata froze at install
    # time — reads the file, which a wheel does not carry.
    here = pathlib.Path(__file__).resolve().parent
    try:
        return (here.parent / "VERSION").read_text().strip()
    except OSError:
        pass
    try:
        return importlib.metadata.version("neuro")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


__version__ = _version()
