
"""Start the Project Red pipeline using the SAY-backend environment."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PROJECT_RED = WORKSPACE / "project_red"


def main():
    pipeline = PROJECT_RED / "pipeline" / "auto_update.py"

    if not pipeline.is_file():
        raise RuntimeError(
            f"Project Red not found at: {PROJECT_RED}\n"
            "Make sure project_red is beside SAY-backend."
        )

    if sys.prefix == sys.base_prefix:
        raise RuntimeError(
            "Backend virtual environment is not active.\n"
            "Activate it using: source venv/bin/activate"
        )

    try:
        from dotenv import dotenv_values
    except ImportError:
        raise RuntimeError(
            "python-dotenv is missing. Install backend requirements first."
        )

    env = os.environ.copy()

    config = dotenv_values(ROOT / ".env")
    for key, value in config.items():
        if value is not None and not env.get(key):
            env[key] = value

    token = env.get("PROJECT_RED_EXPORT_TOKEN")
    pseudonym_key = env.get("PROJECT_RED_PSEUDONYM_KEY")

    if not token or not pseudonym_key:
        raise RuntimeError(
            "PROJECT_RED_EXPORT_TOKEN or PROJECT_RED_PSEUDONYM_KEY "
            "is missing from SAY-backend/.env"
        )

    env["SAY_PROJECT_RED_EXPORT_TOKEN"] = token
    env["SAY_BACKEND_URL"] = env.get(
        "SAY_BACKEND_URL", "http://127.0.0.1:5001"
    )
    env["PYTHONUNBUFFERED"] = "1"

    print("Starting Project Red pipeline...", flush=True)
    print(f"Using Python: {sys.executable}", flush=True)
    print(f"Project directory: {PROJECT_RED}", flush=True)

    subprocess.run(
        [sys.executable, "-m", "pipeline.auto_update"],
        cwd=PROJECT_RED,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
