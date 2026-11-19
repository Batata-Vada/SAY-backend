# SAY backend: current-feature test suite

Prepared against **Batata-Vada/SAY-backend**, default branch commit
`fab7c3ee17fa3dfa6ec473a9d5f4148c06ef7bd5` (2026-11-12).

## Why this exists

The repository already has several historical tests. Some still assume local
username/password login, manual Codeforces handle linking or an old patcher
(`patches/apply_step9.py`), none of which are part of the current Codeforces
OIDC-only backend. In particular, `tests/register_test.py` sends an HTTP
request at module import time. The modernized suite does **not** delete those
files. Instead `pytest.ini` limits default discovery to `tests/current/`.

The suite contains 100 test functions (with additional parameterized cases) and covers:

- Verified HS256 Codeforces OIDC claims; invalid issuer, audience, expiry,
  nonce, subject, handle and signature; state, sessions, CSRF, and logout.
- User isolation and public/private profile fields; avatar processing,
  replacement and validation; education input and visibility.
- Canonical problem forum threads, replies, spoilers, soft delete, votes,
  owner-only edits, admin locks and rate limiting.
- Official Codeforces client, catalog validation/upsert, isolated official
  submissions, sync queue success/failure/requeue, and rating refresh.
- Derived distinct-problem progress, rejudges, snapshot consistency, topic
  mastery and Codeforces **problem** difficulty readiness.
- Explainable recommendations, cold start, final-OK exclusions (including
  unresolved catalog foreign keys), retry modes, unrated fallback, deterministic
  ranking, per-user history and model-version logs.
- Saved SAY source files not being falsely counted as official Codeforces solves.

## Safe installation

From the WSL backend root, with a clean/stashed working tree:

```bash
cd "/home/sidhant/Projects/Batata Vada/SAY-backend"
source .venv/bin/activate
git status
unzip -l SAY_backend_current_tests.zip
unzip -o SAY_backend_current_tests.zip
python -m pip install -r requirements.txt
python -m pytest -v
```

`pytest.ini` and `tests/current/*.py` are additive. They do not change your
application's source code, your production database, your Codeforces account,
or old `tests/*.py` files. They use isolated SQLite under pytest's temporary
folder (`tmp_path`); external `requests` are blocked and Codeforces OIDC is
simulated with locally signed test-only JWTs. **The real application OIDC
callback/identity/session logic is still exercised.**

Run a focused feature:

```bash
python -m pytest tests/current/test_authentication.py -v
python -m pytest tests/current/test_forum.py -v
python -m pytest tests/current/test_codeforces_sync_and_api.py -v
python -m pytest tests/current/test_recommendations.py -v
```

The suite is not a substitute for verifying your **actual Alembic migrations**:

```bash
flask --app main db current
flask --app main db heads
flask --app main db check
flask --app main verify-db-schema
python -m pip check
```

The last four commands inspect your configured application DB. Unlike the
pytest tests, make sure it points at the intended database before running.

## Important: existing tests vs. current tests

Running `python -m pytest -v` runs only `tests/current/`. This is **intentional**:
old tests designed for password login will otherwise report misleading
failures. To audit them separately without running HTTP scripts use e.g.:

```bash
python -m pytest tests/test_difficulty_mastery.py tests/test_progress_aggregation.py -v
```

If any current tests fail, inspect the assertion. They may identify a genuine
backend regression or a difference between your local uncommitted code and the
GitHub branch used for this suite. Do not change an assertion just to make the
suite green; first compare the intended behavior with the source.

## No external API testing

Live Codeforces authorization, the exact registered OIDC callback, browser
SameSite behavior, UI integration, real long-running importer paging, and
production migration/backup behavior require separate manual staging checks.

### Git

The inspected GitHub `.gitignore` already tracks tests. Verify your local
`.gitignore` does not have `/tests`, then:

```bash
git add pytest.ini tests/current/
git status
git commit -m "test: add current OIDC and Phase 1 backend regression suite"
```

No commit/push is performed automatically by this package.
