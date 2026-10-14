import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name, default=""):
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


class Config:
    SECRET_KEY = _env("FLASK_SECRET_KEY", "dev-only-change-me")
    DEBUG = _env("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}

    ORACLE_USER = _env("ORACLE_USER", "hms_app")
    ORACLE_PASSWORD = _env("ORACLE_PASSWORD")
    ORACLE_HOST = _env("ORACLE_HOST", "localhost")
    ORACLE_PORT = int(_env("ORACLE_PORT", "1521") or 1521)
    ORACLE_SID = _env("ORACLE_SID", "XE")
    ORACLE_SERVICE = _env("ORACLE_SERVICE")
    ORACLE_CLIENT_LIB = _env("ORACLE_CLIENT_LIB")

    DEFAULT_ADMIN_USERNAME = _env("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = _env("DEFAULT_ADMIN_PASSWORD", "Admin@123")
    DEFAULT_ADMIN_FULL_NAME = _env("DEFAULT_ADMIN_FULL_NAME", "Hospital Administrator")
