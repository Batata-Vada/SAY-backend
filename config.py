
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
            "http://localhost:3000,http://127.0.0.1:3000"
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

    # Explainable recommendation model weights; normalized and validated at runtime.
    RECOMMENDATION_WEIGHTS = {
        "difficulty": float(os.getenv("REC_WEIGHT_DIFFICULTY", "0.40")),
        "topic": float(os.getenv("REC_WEIGHT_TOPIC", "0.35")),
        "recency": float(os.getenv("REC_WEIGHT_RECENCY", "0.15")),
        "diversity": float(os.getenv("REC_WEIGHT_DIVERSITY", "0.10")),
    }
    RECOMMENDATION_DEFAULT_RATING = int(os.getenv("REC_DEFAULT_RATING", "1000"))
    RECOMMENDATION_CANDIDATE_POOL_CAP = int(os.getenv("REC_CANDIDATE_POOL_CAP", "1200"))

    
    RECOMMENDATION_WEIGHTS = {
        "difficulty": float(
            os.getenv("REC_WEIGHT_DIFFICULTY", "0.40")
        ),
        "topic": float(
            os.getenv("REC_WEIGHT_TOPIC", "0.35")
        ),
        "recency": float(
            os.getenv("REC_WEIGHT_RECENCY", "0.15")
        ),
        "diversity": float(
            os.getenv("REC_WEIGHT_DIVERSITY", "0.10")
        ),
    }

    RECOMMENDATION_DEFAULT_RATING = int(
        os.getenv("REC_DEFAULT_RATING", "1000")
    )

    RECOMMENDATION_CANDIDATE_POOL_CAP = int(
        os.getenv("REC_CANDIDATE_POOL_CAP", "1200")
    )
