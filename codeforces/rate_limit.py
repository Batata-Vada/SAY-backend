"""
All processes MUST use the same CODEFORCES_RATE_LIMIT_FILE, on one host with
working POSIX flock semantics. Multi-host deployments need a centralized limiter.
"""
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from flask import current_app


def _lock_path(filename):
    base = Path(current_app.instance_path)
    base.mkdir(parents=True, exist_ok=True)
    return base / filename


def wait_for_codeforces_slot():
    """Reserve a host-wide API call slot; each request start is >= interval apart."""
    interval = float(current_app.config.get("CODEFORCES_MIN_INTERVAL_SECONDS", 2.1))
    if interval <= 0:  # Useful for mocked test clients only.
        return
    configured = current_app.config.get("CODEFORCES_RATE_LIMIT_FILE")
    path = Path(configured) if configured else _lock_path("codeforces-api-rate.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lockfile:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
        try:
            lockfile.seek(0)
            contents = lockfile.read().strip()
            try:
                next_allowed = float(contents) if contents else 0.0
            except ValueError:
                next_allowed = 0.0
            now = time.time()
            if next_allowed > now:
                time.sleep(next_allowed - now)
            lockfile.seek(0)
            lockfile.truncate()
            lockfile.write(str(time.time() + interval))
            lockfile.flush()
            os.fsync(lockfile.fileno())
        finally:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_account_sync(account_id):
    """Reject concurrent syncs of the same account on this host."""
    path = _lock_path(f"codeforces-account-{account_id}.lock")
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("This Codeforces account is already syncing") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
