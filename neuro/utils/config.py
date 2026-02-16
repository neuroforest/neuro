import os
import dotenv
import logging
import inspect

from neuro.utils import build_utils


CONFIG_INITIALIZED = False


def get_importing_module():
    frame = inspect.currentframe().f_back
    while frame:
        module = inspect.getmodule(frame)
        if module and module.__name__ != __name__:
            return module.__name__
        frame = frame.f_back
    return None


def load_env_files(env_path):
    """Loads environment variables from .env files."""
    if not env_path:
        env_path = os.getenv("NF_DIR", os.getcwd())
    with build_utils.chdir(env_path):
        default_env_path = os.path.abspath(".env.defaults")
        dotenv.load_dotenv(default_env_path)
        logging.debug(f"Setting env {default_env_path}")
        if os.getenv("ENVIRONMENT") == "TESTING":
            testing_env_path = os.path.abspath(".env.testing")
            if os.path.exists(testing_env_path):
                dotenv.load_dotenv(testing_env_path, override=True)
                logging.debug(f"Setting env {testing_env_path}")
        else:
            env_path = os.path.abspath(".env")
            dotenv.load_dotenv(env_path, override=True)
            logging.debug(f"Setting env {env_path}")


def config_logging():
    log_level = os.getenv("LOGGING", "WARNING")
    log_format = os.getenv("LOGGING_FORMAT")

    log_level = getattr(logging, log_level, logging.WARNING)
    logging.basicConfig(level=log_level, format=log_format)
    logger = logging.getLogger(__name__)
    logger.info(f"CLI Logging initialized with level {logger.getEffectiveLevel()}")


def main(env_path=None):
    global CONFIG_INITIALIZED
    if CONFIG_INITIALIZED:
        return
    else:
        load_env_files(env_path)
        config_logging()
        CONFIG_INITIALIZED = True
