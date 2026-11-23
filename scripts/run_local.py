"""Run SAY-frontend, SAY-backend, Codeforces watcher, and Project Red together.

Use the existing sibling virtual environments; do not mutate databases or secrets.
"""
import argparse
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
FRONTEND = WORKSPACE / "SAY-frontend"
PROJECT_RED = WORKSPACE / "project_red"


def executable(path):
    if not path.is_file():
        raise RuntimeError(f"Missing executable {path}. Install dependencies in that repository first.")
    return str(path)


def resolve():
    backend_python = executable(ROOT / ".venv/bin/python")
    project_python = executable(PROJECT_RED / ".venv/bin/python")
    if not (PROJECT_RED / "pipeline/auto_update.py").is_file():
        raise RuntimeError(
            "Project Red automation is missing. Update the sibling project_red repository "
            "with git pull --ff-only origin main before starting SAY."
        )
    if not (FRONTEND / "package.json").is_file():
        raise RuntimeError(f"Missing frontend repository: {FRONTEND}")
    if not (FRONTEND / "node_modules").is_dir():
        raise RuntimeError("Install frontend dependencies with npm ci before running SAY")
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is unavailable. Install Node.js and npm.")
    env = os.environ.copy()
    backend_config = dotenv_values(ROOT / ".env")
    for key, value in backend_config.items():
        if value is not None:
            env.setdefault(key, value)
    token = env.get("PROJECT_RED_EXPORT_TOKEN", "")
    if not token:
        raise RuntimeError("Configure PROJECT_RED_EXPORT_TOKEN in SAY-backend/.env")
    if not env.get("PROJECT_RED_PSEUDONYM_KEY"):
        raise RuntimeError("Configure PROJECT_RED_PSEUDONYM_KEY in SAY-backend/.env")
    env["SAY_BACKEND_URL"] = env.get("SAY_BACKEND_URL", "http://127.0.0.1:5001")
    env["SAY_PROJECT_RED_EXPORT_TOKEN"] = token
    env["NEXT_PUBLIC_API_URL"] = env.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:5001")
    # Relative model paths in the backend resolve from the backend repository root.
    # Explicit deployment model paths remain authoritative.
    env.setdefault("PROJECT_RED_MODEL_PATH", str(PROJECT_RED / "artifacts/online_v1/model.json"))
    env["PYTHONUNBUFFERED"] = "1"
    return backend_python, project_python, npm, env


def check_port(port, name):
    """Fail before starting any services if a local development port is occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        if connection.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(
                f"{name} cannot start: port {port} is already in use. "
                "Stop the existing service before running the all-in-one launcher."
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-frontend", action="store_true", help="Skip starting Next.js")
    parser.add_argument("--no-server", action="store_true", help="Skip starting Flask")
    args = parser.parse_args()
    backend_python, project_python, npm, env = resolve()
    if not args.no_server:
        check_port(5001, "Flask")
    if not args.no_frontend:
        check_port(3000, "Next.js")

    processes = []
    commands = [
        ("Codeforces watcher", [backend_python, "-m", "flask", "--app", "main", "watch-cf-practice"], ROOT),
        ("Project Red pipeline", [project_python, "-m", "pipeline.auto_update"], PROJECT_RED),
    ]
    if not args.no_server:
        commands.insert(0, ("Flask API", [backend_python, "main.py"], ROOT))
    if not args.no_frontend:
        commands.append(("Next.js", [npm, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000"], FRONTEND))

    def stop_all():
        # Each process was started in its own session; terminate the full group,
        # including the Next.js child spawned by npm, not just the npm parent.
        for name, child in processes:
            print(f"Stopping {name}", flush=True)
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for _, child in processes:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()

    try:
        for name, command, cwd in commands:
            print(f"Starting {name}...", flush=True)
            child = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True)
            processes.append((name, child))
        print("SAY local services started. Press Ctrl+C to stop all.", flush=True)
        while True:
            for name, child in processes:
                code = child.poll()
                if code is not None:
                    raise RuntimeError(f"{name} exited with status {code}")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    main()
