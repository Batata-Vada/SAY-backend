# SAY Backend

SAY (Simplifying Algorithms for You) is a learning platform for competitive programming and data structures and algorithms practice. The Flask backend connects to Codeforces for verified sign-in, problem data, submissions, progress tracking, and personalized recommendations. It also provides SAY profiles and problem discussions.

## Setup

Use Python 3 and install the dependencies in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

```bash
python - <<'PY'
import sqlite3
from datetime import datetime
from pathlib import Path
src=Path('instance/app.db')
if not src.is_file(): raise SystemExit('Check flask --app main db-info first')
dst=src.with_name('app-before-oidc-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
with sqlite3.connect(src) as a, sqlite3.connect(dst) as b: a.backup(b)
print('Backup:',dst)
PY
```

**Never delete `app.db`, run `db.create_all()` against production, stamp a missing migration, or auto-merge old SAY users by handle.**

## 2. Create a Codeforces OAuth application

1. Sign in to Codeforces and open https://codeforces.com/settings/api.
2. Create an OAuth application (Codeforces's OIDC announcement points to API settings).
3. For local development, register the exact callback URI `http://127.0.0.1:5001/auth/codeforces/callback` **if permitted by Codeforces**. If loopback HTTP callbacks aren't accepted, use an HTTPS development origin and register that exact URI.
4. Obtain `client_id` and `client_secret` for that OAuth app. Keep the secret on the backend only.
5. Configure `.env` (never commit):

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///app.db
CODEFORCES_OIDC_CLIENT_ID=REPLACE_WITH_OAUTH_APP_ID
CODEFORCES_OIDC_CLIENT_SECRET=REPLACE_WITH_OAUTH_APP_SECRET
CODEFORCES_OIDC_REDIRECT_URI=http://127.0.0.1:5001/auth/codeforces/callback
SAY_FRONTEND_URL=http://127.0.0.1:3000
CORS_ORIGINS=http://127.0.0.1:3000
SAY_COOKIE_SECURE=false
```

Register the matching redirect URI in your Codeforces OAuth application. Ensure that the frontend origin, backend origin, and cookie settings are compatible. For deployment, use HTTPS, a persistent database, an appropriate secret key, explicitly configured CORS origins, and `SAY_COOKIE_SECURE=true`.

Apply the database migrations and start the application:

```bash
flask --app main db upgrade
python main.py
```

The default local backend address is `http://127.0.0.1:5001`. You can configure `HOST` and `PORT`.

## Authentication

`http://127.0.0.1:5001/auth/codeforces/login`

Open `/auth/codeforces/login` in a browser to sign in through Codeforces. The callback verifies the OpenID Connect identity and creates a SAY session.

- `GET /auth/session` — current authenticated session
- `GET /auth/csrf` — CSRF token for authenticated write requests
- `POST /auth/logout` — end the session
- `GET /api/codeforces/account` — linked Codeforces account

The browser uses the `say_session` HttpOnly cookie. Frontend requests must include credentials; cookie-authenticated `POST`, `PUT`, `PATCH`, and `DELETE` requests must send the `X-SAY-CSRF` header. Password-based SAY registration and login are no longer supported. A Codeforces handle alone is not proof of account ownership.

## Codeforces data

Import the problem catalog and process queued submission updates using the Flask CLI:

```bash
flask --app main sync-cf-problems
flask --app main process-cf-sync-queue --limit 1
```

Additional commands include `sync-cf-submissions`, `reconcile-cf-submissions`, `rebuild-cf-progress`, and `rebuild-cf-skills`. Run `flask --app main --help` to view available commands and options.

Important API endpoints:

| Endpoint | Purpose |
| --- | --- |
| `POST /api/codeforces/sync` | Queue a Codeforces account update |
| `GET /api/codeforces/sync` | View sync status |
| `GET /api/codeforces/submissions` | View official submissions |
| `GET /api/me/progress` | View problem progress |
| `GET /api/me/mastery` | View topic mastery |
| `GET /api/me/difficulty-readiness` | View difficulty readiness |
| `GET /api/recommendations` | Get personalized recommendations |

SAY uses Codeforces problem identifiers for its catalog and stores progress against SAY user IDs. Saved source code is separate from official Codeforces submissions.

## Profiles and discussions

SAY supports user profiles, education details, avatar uploads, and problem-specific discussions. Notable routes include:

- `GET /api/me/say-profile` and `PATCH /api/me/say-profile` for SAY profile details
- `POST /api/me/avatar` for avatar uploads
- `GET /api/problems/codeforces/<contest_id>/<index>` to resolve a Codeforces problem
- `GET /api/problems/<problem_id>/forum/threads` for discussions about a problem
- `/api/forum/threads/<thread_id>` and `/api/forum/threads/<thread_id>/replies` for threads and replies

Forum content has ownership checks, moderation controls, and optional spoiler hiding. Avatar files are stored locally under `instance/uploads/avatars`; production deployments need persistent storage for uploads.

## Database and administration

Database changes are managed with Flask-Migrate/Alembic. Back up the configured database before migrating production data.

```bash
flask --app main db current
flask --app main db heads
flask --app main db upgrade
flask --app main verify-db-schema
```

Use `flask --app main grant-admin <username>` only from a trusted server shell. The `adopt-legacy-oidc` command exists for carefully reviewed account migrations; never merge users based solely on matching Codeforces handles.

The `rest_client/codeforces_oidc_forum.http` file contains example API requests. Keep real session cookies and credentials in private, ignored local files.

## Adaptive recommendations

The frontend uses the unchanged `GET /api/recommendations?limit=10&mode=new` endpoint.
SAY retains its deterministic ranking, solved-problem exclusions, difficulty fallback,
audit logs, and authenticated practice-session routes. The response fields
`recommendation_engine`, `model_version`, `selection_reason`,
`difficulty_prediction`, and `recommendations` remain available.

Project Red is disabled by default. Enable it only after deploying a validated
real-outcome model artifact:

```dotenv
PROJECT_RED_ENABLED=false
PROJECT_RED_MIN_TIMED_SOLVES=5
PROJECT_RED_MODEL_PATH=recommendations/artifacts/project_red_real_v1/model.json
PROJECT_RED_EXPORT_TOKEN=YOUR_PRIVATE_EXPORT_TOKEN
PROJECT_RED_PSEUDONYM_KEY=YOUR_SEPARATE_PRIVATE_PSEUDONYM_KEY
```

Set the two secrets to independently generated random values; do not commit them.
The export token is used **only by Project Red's private ingestion client**. Do not
send it from the browser. Keep the HTTPS exporter behind your server firewall or
gateway outside local development.

### Training export and feature contract

`GET /api/internal/project-red/events?after_id=0&limit=200` requires
`Authorization: Bearer <PROJECT_RED_EXPORT_TOKEN>` and responds with
`schema_version: 2`, `feature_contract: say-practice-v1`, `events`, and
`next_after_id`. Cursor pagination uses monotonically increasing practice-session IDs.
Rerun a complete export when training because older session outcomes can change after
Codeforces rejudging or synchronization. Raw events are private behavioral records,
even though user IDs are pseudonymized.

Each event includes `outcome_status` (`SOLVED`, `FAILED`, `UNKNOWN`),
`official_solved`, `final_failure_observed`, `previously_solved`,
`problem_rating`, `duration_seconds`, and `history_features`.
Only eligible first-time `SOLVED` and `FAILED` events should be used as binary labels.
`FAILED` requires an observed final unsuccessful individual submission,
no pending decision, and a successful full-history sync following the practice session.
A recorded start/finish without an official attempt is **not** a verified failure.
There may be no eligible examples until users have accumulated sufficient observed
history and a full synchronization has completed.

`history_features` is calculated server-side using the exact same feature extractor
as inference, as of the target session's start time. It selects the most recent 150
completed sessions strictly before that time and up to 30 distinct, officially verified
timed solves observed before that time. Five such solves are required by default.
The current model contract uses these ordered inputs:

```text
candidate_rating
last_problem_rating
mean_solve_time_minutes
time_std_minutes
timed_solved_count
last_problem_solve_time_minutes
```

A null `history_features` means no historically observable inference profile exists.
Existing imported Codeforces submissions do not have known original first-observation
times. A later sync will record a **new** observation timestamp rather than invent
historical provenance; it will not retroactively create older historical features.

### Validated real-model serving

Model training, evaluation, calibration, and artifact publication belong to
`project_red`, not this Flask application. A compatible `model.json` must contain:

```json
{
  "artifact_schema_version": 1,
  "feature_contract": "say-practice-v1",
  "model_type": "logistic-regression",
  "model_version": "project-red-real-v1",
  "features": [
    "candidate_rating", "last_problem_rating",
    "mean_solve_time_minutes", "time_std_minutes",
    "timed_solved_count", "last_problem_solve_time_minutes"
  ],
  "x_mean": [0, 0, 0, 0, 0, 0],
  "x_scale": [1, 1, 1, 1, 1, 1],
  "coef": [-0.1, 0, 0, 0, 0, 0],
  "intercept": 0,
  "target_probability": 0.60,
  "acceptable_probability_range": [0.45, 0.75],
  "rating_grid": [800, 3500, 100]
}
```

**The numbers above describe artifact structure only, not a trained model.**
Never publish or enable a dummy artifact. SAY validates model type, schema,
feature order, finite coefficients and difficulty monotonicity. It derives an
appropriate window from the accepted probability range and falls back to the
existing deterministic recommender if the artifact is absent, invalid, or does
not produce a suitable difficulty window. Model version is taken from the
artifact when that model is actually selected. To deploy a replacement model,
update the artifact at a new versioned path and restart Flask; the artifact loader
caches models within each process.

The server's `POST /api/me/practice-sessions` still only requires a numeric
`problem_id`. An optional `recommendation_run_id` can now be supplied to link
practice to a recommendation previously generated for the same user and problem.
Existing frontend requests and response keys remain supported.

### Deployment and database upgrade

This release adds nullable Codeforces submission observation timestamps, the last
successful full-sync timestamp, and optional practice recommendation attribution.
These require a database migration before restarting the new application:

```bash
flask --app main db current
flask --app main db heads
# Back up the SQLite file instance/app.db before upgrading.
flask --app main db upgrade
flask --app main verify-db-schema
```

Do not stamp an older database without reconciling its actual schema. After migration,
run a **full** Codeforces sync to establish coverage and observation timestamps:

```bash
flask --app main sync-cf-submissions --account-id <ID> --full
```

Inspect `flask --app main sync-cf-submissions --help` for the exact installed
CLI option names. Existing queued sync workers continue to work.

Legacy `project_red_v5` files remain in Git history for reproducibility but
are not loaded by the new serving path. The old model was trained on synthetic
difficulty-window targets; SAY does not silently fall back to that model.

## Automatic Codeforces practice synchronization

Run a single persistent watcher alongside the Flask web process:

```bash
flask --app main watch-cf-practice
```

The watcher checks active practice sessions approximately every 5 seconds by default,
subject to the shared Codeforces API rate limiter and number of active users.
It runs in a separate process, not within an HTTP request or Flask thread.
It also processes jobs submitted through the existing `/api/codeforces/sync`
queue, so no manual queue-worker command is needed while it is running.
Run only one watcher on a local SQLite installation.

Optional environment variables:

```dotenv
CODEFORCES_WATCH_INTERVAL_SECONDS=5
CODEFORCES_WATCH_BATCH_SIZE=10
CODEFORCES_WATCH_PAGE_LIMIT=10
```

On an official individual `OK` verdict with `TESTS`, the watcher finishes
the matching active session using the Codeforces submission timestamp. Other
verdicts keep the timer active. Progress and skill estimates are rebuilt after
new or changed official submissions. The existing practice session listing
now also exposes `latest_verdict`, `latest_submission_id`,
`elapsed_seconds`, and `last_checked_at`. Reloading the frontend does
not reset the server-side timer.

Practice shorter than 60 seconds and sessions exceeding four hours do not
qualify as timed training events. Recent polling does not assert complete
submission-history coverage; the standard full sync is still needed to
establish reliable failed-outcome labels for Project Red.

### Diagnosing practice synchronization

With the persistent watcher stopped, run a single real Codeforces poll:

```bash
flask --app main watch-cf-practice --once
```

The summary reports eligible accounts, due accounts, successful/failed account
checks, and completed sessions. The continuous watcher also prints a startup
summary and per-poll status. If `eligible_accounts` is zero, check whether
the linked account is verified and whether there is an active session or one
finished within the last 15 minutes. Finished sessions remain finished:
delayed Codeforces acceptance can update their official verification status
without changing the user's recorded finish time. The watcher does not modify
the five-prior-timed-solves rule for Project Red training.

## One-command local development

With the three sibling repositories in the same parent directory, use:

```bash
cd SAY-backend
.venv/bin/python scripts/run_local.py
```

The launcher starts Flask on port 5001, Next.js on port 3000, the Codeforces
practice watcher, and the Project Red pipeline. It uses the existing
`.venv` environments in SAY-backend and project_red, plus `npm ci`-installed
frontend modules. Ensure the ports are free and the database is migrated
before launching. Press Ctrl+C to shut down the processes.

It reads the existing local `SAY-backend/.env` configuration; no user secrets
are added to Git. In particular, it maps `PROJECT_RED_EXPORT_TOKEN` to
Project Red's private `SAY_PROJECT_RED_EXPORT_TOKEN` environment variable,
and sets the default model location to the sibling online artifact.
Environment variables already explicitly set by the operator take precedence.

The watcher handles active practice polling, queued Codeforces account syncs,
a full-history refresh for one due account per hour (default 24-hour
per-account cadence), and a 24-hour problem-catalog refresh. The Project Red
worker completely re-exports events, rebuilds `training_rows.csv`, and
updates the online learner every 180 seconds. Missing historical features do
not become fabricated training rows. Failures are logged and retried in the
next cycle. All live services must remain running for automation.

Optional backend settings:

```dotenv
CODEFORCES_FULL_SYNC_INTERVAL_HOURS=24
CODEFORCES_AUTO_CATALOG_SYNC=true
CODEFORCES_CATALOG_INTERVAL_HOURS=24
PROJECT_RED_PIPELINE_INTERVAL_SECONDS=180
```

The backend now reloads model JSON when the artifact changes on disk rather
than keeping the first loaded artifact indefinitely in memory. Project Red
inference still requires `PROJECT_RED_ENABLED=true` explicitly, and
should only be enabled after the online artifact has been evaluated on
real held-out data. The default remains `false` for safety.

### Automatic progress and skill freshness

An unchanged Codeforces account synchronization is not a change in skill
evidence. The mastery endpoint validates the materialized progress watermark
and a digest of the official problem evidence, not merely the account's
`last_synced_at` timestamp. This avoids false 409 responses after successful
no-change polling.

The persistent `watch-cf-practice` worker also checks up to five verified
accounts per minute for stale progress or skills, cycling across accounts.
It rebuilds progress first when official evidence changed, then refreshes
skill estimates only if their evidence digest or model version is outdated.
This repairs data left stale by an interrupted sync or catalog updates without
requiring a manual `rebuild-cf-progress`/`rebuild-cf-skills` command.

If needed, restart the worker after updating this code. Its repair log line
reads `Codeforces profile repair: ...` when a stale profile was fixed.

### Diagnosing empty Project Red datasets

`data/say_practice_events.jsonl` is not the same as `training_rows.csv`.
The exporter includes qualifying finished practice sessions even when their
outcomes are UNKNOWN or their historical features are unavailable.
The dataset builder excludes unrated targets, previously solved targets,
UNKNOWN outcomes, and targets without enough earlier timed history.
A blank CSV apart from headers means there are currently zero eligible
training labels; it is **not** evidence that the worker is broken.

The backend requires five **distinct** rated, officially accepted, timed
practice solves from the same active account, with final verdicts first
observed **before the next target session starts**. Imported submissions
without tracked SAY timers cannot be treated as timed solves. A later
Codeforces submission after the session's recorded finish time is not
retroactively inside that session.

Authenticated `GET /api/me/practice-sessions/readiness` returns the number
of real verified timed solves available for **future** sessions, remaining
solves needed, and source sync status. The frontend surfaces this on Practice.
This is a historical-data readiness indicator, not proof that the online model
has trained or that Project Red inference was selected.

`CODEFORCES_WATCH_INTERVAL_SECONDS` defaults to 5 and accepts values 5–3600.
A local `.env` value takes precedence over the default; update any previous
`CODEFORCES_WATCH_INTERVAL_SECONDS=30` setting to 5. Worker cycles target
five-second starts but can take longer when Codeforces is slow, history
paging is required, multiple users are active, or the host-wide rate limiter
delays calls. Project Red's separate dataset-export interval is 180 seconds.

### Project Red eligibility without contest participation

SAY does not require any minimum number of rated Codeforces contests or
total solved problems before trying Project Red inference. The response
continues to report solved-problem and rated-contest counts for context only.
A synchronized linked account can attempt inference when
`PROJECT_RED_ENABLED=true` and the required verified, timed practice
features are available. The separate five-distinct-prior-timed-solves
historical training requirement remains unchanged; the recommender falls
back safely when features, a validated model artifact, or suitable candidate
problems are unavailable.
