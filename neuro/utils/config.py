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
    """Set NF_CONFIG, NF_DATA, NF_STATE, NF_CACHE from XDG base directories.

    NF_CONFIG is shared across environments (holds env files).
    NF_DATA uses XDG_DATA_HOME for production, XDG_STATE_HOME for develop/testing.
    NF_STATE, NF_CACHE are always namespaced per environment.
    """
    home = Path.home()
    app_name = os.environ["APP_NAME"].lower()
    env_name = os.environ["ENVIRONMENT"].lower()

    # Config is shared (holds env.develop, env.testing, env.production)
    if "NF_CONFIG" not in os.environ:
        base = os.getenv("XDG_CONFIG_HOME", home / ".config")
        os.environ["NF_CONFIG"] = str(Path(base) / app_name)
    logging.debug(f"XDG path NF_CONFIG={os.environ['NF_CONFIG']}")

    # Data: production uses XDG_DATA_HOME, develop/testing use XDG_STATE_HOME
    if "NF_DATA" not in os.environ:
        if env_name == "production":
            base = os.getenv("XDG_DATA_HOME", home / ".local" / "share")
            os.environ["NF_DATA"] = str(Path(base) / app_name)
        else:
            base = os.getenv("XDG_STATE_HOME", home / ".local" / "state")
            os.environ["NF_DATA"] = str(Path(base) / app_name / env_name)
    logging.debug(f"XDG path NF_DATA={os.environ['NF_DATA']}")

    # State and cache: always namespaced per environment
    xdg_map = {
        "NF_STATE": os.getenv("XDG_STATE_HOME", home / ".local" / "state"),
        "NF_CACHE": os.getenv("XDG_CACHE_HOME", home / ".cache"),
    }

    for var, base in xdg_map.items():
        if var not in os.environ:
            os.environ[var] = str(Path(base) / app_name / env_name)
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


VALID_ENVIRONMENTS = frozenset({"DEVELOP", "TESTING", "PRODUCTION"})


def load_env_files(env_path):
    """Loads environment variables from .env files.

    Loading order:
        1. .env           — tracked defaults from NF_DIR (repo baseline).
        2. XDG paths      — resolve NF_CONFIG, NF_DATA, NF_STATE, NF_CACHE.
        3. env.{env}      — environment-specific overrides from $NF_CONFIG/.
        4. (system mode)  — remap relative user paths to XDG locations.
    """
    if not env_path:
        env_path = os.getenv("NF_DIR", os.getcwd())

    mode = detect_mode()
    os.environ["NF_MODE"] = mode
    logging.debug(f"Config mode: {mode}")

    with build_utils.chdir(env_path):
        # 1. Repo defaults
        default_env_path = os.path.abspath(".env")
        dotenv.load_dotenv(default_env_path)
        logging.debug(f"Setting env {default_env_path}")

        if not os.getenv("ENVIRONMENT"):
            os.environ["ENVIRONMENT"] = "DEVELOP"

        # 2. XDG paths (always, not just system mode)
        resolve_xdg_paths()

        # 3. Environment-specific overrides from XDG
        env_name = os.environ["ENVIRONMENT"]
        if env_name not in VALID_ENVIRONMENTS:
            logging.warning(f"Unknown ENVIRONMENT: {env_name}")
        nf_config = os.environ.get("NF_CONFIG", "")
        env_file = os.path.join(nf_config, f"env.{env_name.lower()}")
        if os.path.exists(env_file):
            dotenv.load_dotenv(env_file, override=True)
            logging.debug(f"Setting env {env_file}")

        # 4. System mode: remap relative paths to XDG
        if mode == "system":
            resolve_user_paths()


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
