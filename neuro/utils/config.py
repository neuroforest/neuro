import os
import dotenv


def load_env_files():
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    dotenv.load_dotenv(os.path.join(base_path, ".env.defaults"))
    dotenv.load_dotenv(os.path.join(base_path, ".env"), override=True)
