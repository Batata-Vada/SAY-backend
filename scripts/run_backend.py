
"""Run the Flask API and Codeforces practice watcher together."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def wait_for_server(process, url, timeout=30):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Flask server exited with status {process.returncode}"
            )

        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    print("Flask server is ready.", flush=True)
                    return
        except Exception:
            pass

        time.sleep(0.5)

    raise RuntimeError("Flask server did not become ready within 30 seconds.")


def main():
    if sys.prefix == sys.base_prefix:
        raise RuntimeError(
            "Backend virtual environment is not active.\n"
            "Run: source venv/bin/activate"
        )

    load_dotenv(ROOT / ".env")
    env = os.environ.copy()

    host = env.get("HOST", "127.0.0.1")
    port = int(env.get("PORT", "5001"))
    health_url = f"http://{host}:{port}/"

    processes = []

    try:
        print("\nStarting SAY Flask backend...", flush=True)

        backend = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=ROOT,
            env=env,
        )
        processes.append(("Flask backend", backend))

        wait_for_server(backend, health_url)

        print("\nStarting Codeforces practice watcher...", flush=True)

        watcher = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "flask",
                "--app",
                "main",
                "watch-cf-practice",
            ],
            cwd=ROOT,
            env=env,
        )
        processes.append(("Codeforces watcher", watcher))

        print("\nBoth services are running.", flush=True)
        print("Flask:     " + health_url, flush=True)
        print("Watcher:   Active", flush=True)
        print("\nPress Ctrl+C to stop both services.\n", flush=True)

        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(
                        f"{name} stopped unexpectedly (exit code {code})."
                    )

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping services...", flush=True)

    finally:
        for name, process in reversed(processes):
            if process.poll() is None:
                print(f"Stopping {name}...", flush=True)
                process.terminate()

        for _, process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        print("Backend services stopped.", flush=True)


if __name__ == "__main__":
    main()
