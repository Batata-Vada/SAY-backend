
"""Environment-driven configuration for SAY."""

import os
from dotenv import load_dotenv

load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {
        "1", "true", "yes", "on"
    }


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///app.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]

    CODEFORCES_TIMEOUT_SECONDS = int(
        os.getenv("CODEFORCES_TIMEOUT_SECONDS", "30")
    )

    SESSION_MAX_AGE_SECONDS = int(
        os.getenv("SESSION_MAX_AGE_SECONDS", "604800")
    )

    TESTING = env_bool("TESTING")
    DEBUG = env_bool("DEBUG")