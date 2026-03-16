import os
import dotenv
import logging
import inspect
from pathlib import Path

from neuro.utils import build_utils


CONFIG_INITIALIZED = False

# Paths that hold per-user data, mapped to their XDG target directory variable
USER_DATA_PATHS = {"STORAGE": "NF_DATA", "ARCHIVE": "NF_DATA"}
USER_STATE_PATHS = {"LOGS": "NF_STATE"}


def get_importing_module():
    frame = inspect.currentframe().f_back
    while frame:
        module = inspect.getmodule(frame)
        if module and module.__name__ != __name__:
            return module.__name__
        frame = frame.f_back
    return None


def detect_mode():
    """Detect whether we're running in dev or system mode.

    Returns "system" if NF_MODE is explicitly set, or if the .env file
    at NF_DIR is not writable by the current user. Otherwise returns "dev".
    """
    mode = os.getenv("NF_MODE")
    if mode:
        return mode

    nf_dir = os.getenv("NF_DIR", os.getcwd())
    env_file = os.path.join(nf_dir, ".env")
    if os.path.exists(env_file) and not os.access(env_file, os.W_OK):
        return "system"

    return "dev"


def resolve_xdg_paths():
    """Set NF_CONFIG, NF_DATA, NF_STATE, NF_CACHE from XDG base directories."""
    home = Path.home()

    app_name = os.environ["APP_NAME"].lower()

    xdg_map = {
        "NF_CONFIG": (os.getenv("XDG_CONFIG_HOME", home / ".config"), app_name),
        "NF_DATA": (os.getenv("XDG_DATA_HOME", home / ".local" / "share"), app_name),
        "NF_STATE": (os.getenv("XDG_STATE_HOME", home / ".local" / "state"), app_name),
        "NF_CACHE": (os.getenv("XDG_CACHE_HOME", home / ".cache"), app_name),
    }

    for var, (base, subdir) in xdg_map.items():
        if var not in os.environ:
            os.environ[var] = str(Path(base) / subdir)
        logging.debug(f"XDG path {var}={os.environ[var]}")


def resolve_user_paths():
    """In system mode, remap relative user paths to absolute XDG locations.

    For example, STORAGE=storage becomes $NF_DATA/storage.
    """
    for env_var, xdg_var in {**USER_DATA_PATHS, **USER_STATE_PATHS}.items():
        value = os.getenv(env_var, "")
        if value and not os.path.isabs(value):
            xdg_base = os.environ[xdg_var]
            os.environ[env_var] = os.path.join(xdg_base, value)
            logging.debug(f"Remapped {env_var}={os.environ[env_var]}")


def load_env_files(env_path):
    """Loads environment variables from .env files.

    Dev mode:
        .env        — tracked defaults, committed to the repository.
        .env.local  — local overrides, gitignored (from NF_DIR).

    System mode:
        .env        — read-only system baseline (from NF_DIR).
        XDG paths resolved + relative user paths remapped.
        .env.local  — per-user overrides (from $NF_CONFIG/).
    """
    if not env_path:
        env_path = os.getenv("NF_DIR", os.getcwd())

    mode = detect_mode()
    os.environ["NF_MODE"] = mode
    logging.debug(f"Config mode: {mode}")

    with build_utils.chdir(env_path):
        default_env_path = os.path.abspath(".env")
        dotenv.load_dotenv(default_env_path)
        logging.debug(f"Setting env {default_env_path}")

        if not os.getenv("ENVIRONMENT"):
            os.environ["ENVIRONMENT"] = "DEVELOP"

        if mode == "system":
            resolve_xdg_paths()
            resolve_user_paths()

            nf_config = os.environ.get("NF_CONFIG", "")
            user_env_path = os.path.join(nf_config, ".env.local")
            dotenv.load_dotenv(user_env_path, override=True)
            logging.debug(f"Setting env {user_env_path}")

            if os.getenv("ENVIRONMENT") == "TESTING":
                testing_env_path = os.path.abspath(".env.testing")
                if os.path.exists(testing_env_path):
                    dotenv.load_dotenv(testing_env_path, override=True)
                    logging.debug(f"Setting env {testing_env_path}")
        else:
            environment = os.getenv("ENVIRONMENT")
            if environment == "TESTING":
                testing_env_path = os.path.abspath(".env.testing")
                if os.path.exists(testing_env_path):
                    dotenv.load_dotenv(testing_env_path, override=True)
                    logging.debug(f"Setting env {testing_env_path}")
            elif environment == "DEVELOP":
                env_path = os.path.abspath(".env.local")
                dotenv.load_dotenv(env_path, override=True)
                logging.debug(f"Setting env {env_path}")


def config_logging():
    log_level = os.getenv("LOGGING", "WARNING")
    log_format = os.getenv("LOGGING_FORMAT")

    log_level = getattr(logging, log_level, logging.WARNING)
    handlers = []

    if os.getenv("ENVIRONMENT") == "PRODUCTION":
        nf_state = os.getenv("NF_STATE", "")
        if nf_state:
            log_dir = os.path.join(nf_state, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "desktop.log")
            handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=log_level, format=log_format, handlers=handlers or None)
    logger = logging.getLogger(__name__)
    logger.info(f"CLI Logging initialized with level {logger.getEffectiveLevel()}")


def main(env_path=None):
    global CONFIG_INITIALIZED
    environment = os.getenv("ENVIRONMENT")
    if CONFIG_INITIALIZED and CONFIG_INITIALIZED == environment:
        return
    load_env_files(env_path)
    config_logging()
    CONFIG_INITIALIZED = os.getenv("ENVIRONMENT")
