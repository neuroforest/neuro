import os
import dotenv
import logging
import inspect


CONFIG_INITIALIZED = False


def get_importing_module():
    frame = inspect.currentframe().f_back
    while frame:
        module = inspect.getmodule(frame)
        if module and module.__name__ != __name__:
            return module.__name__
        frame = frame.f_back
    return None


def load_env_files():
    """Loads environment variables from .env files."""
    current_dir = os.getcwd()
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    dotenv.load_dotenv(os.path.abspath(".env.defaults"))
    if os.getenv("ENVIRONMENT") == "TESTING":
        if os.path.exists(".env.testing"):
            dotenv.load_dotenv(os.path.abspath(".env.testing"), override=True)
    else:
        # print(f"Overriding .env.defaults with .env (called by {get_importing_module()})")
        dotenv.load_dotenv(os.path.abspath(".env"), override=True)
    os.chdir(current_dir)


def config_logging():
    log_level = os.getenv("LOGGING", "WARNING")
    log_format = os.getenv("LOGGING_FORMAT")

    log_level = getattr(logging, log_level, logging.WARNING)
    logging.basicConfig(level=log_level, format=log_format)
    logger = logging.getLogger(__name__)
    logger.info(f"CLI Logging initialized with level {logger.getEffectiveLevel()}")


def main():
    global CONFIG_INITIALIZED
    if CONFIG_INITIALIZED:
        return
    else:
        load_env_files()
        config_logging()
        CONFIG_INITIALIZED = True


main()
