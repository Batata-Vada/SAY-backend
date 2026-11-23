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

Create a local `.env` file (do not commit it) with settings appropriate for your environment:

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///app.db
CODEFORCES_OIDC_CLIENT_ID=your-client-id
CODEFORCES_OIDC_CLIENT_SECRET=your-client-secret
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

The Practice page requests `GET /api/recommendations?limit=10&mode=new` and displays
the returned Codeforces problem metadata and direct problem links. The backend
preserves solved-problem exclusions, topic scoring, retry selection and recommendation
logs. The same endpoint supports `retry` and `mixed` modes.

The default recommender is used while **both** the distinct solved-problem count is
at most 10 and the number of rated Codeforces contests is at most 5. Crossing either
threshold makes the user eligible for Project Red v5, provided their account is verified,
Codeforces history is successfully synchronized, the user has a current Codeforces
contest rating, and enough genuine practice timings have been verified against official
individual Codeforces accepted submissions. Otherwise the default recommender remains
active. Model inference failures also return to the default recommender.

The Project Red v5 ONNX model and its external data are under
`recommendations/artifacts/project_red_v5/`. The compatible scaler values were
reconstructed from Project Red's v5 training split rather than using its saved scalers,
which were incorrectly refitted on its test split. The existing model was trained on
synthetic target data, so the predicted bands should be treated as experimental.
Use `PROJECT_RED_ENABLED=false` to disable model inference. The number of required
verified timed solves defaults to five and can be configured with
`PROJECT_RED_MIN_TIMED_SOLVES`.

After updating the repository, install the new runtime dependencies and migrate
the database before serving requests:

```bash
pip install -r requirements.txt
flask --app main db upgrade
```

Refresh Codeforces submissions through the existing sync worker, which now also
updates the current rating and rated-contest count. A worker must be running for
queued sync jobs to finish:

```bash
flask --app main process-cf-sync-queue --limit 10
```

`POST /api/me/practice-sessions` with a canonical numeric `problem_id` starts
a server-timed session. `POST /api/me/practice-sessions/<id>/finish` completes it.
`GET /api/me/practice-sessions` lists up to 30 recent sessions. Session timings
contribute to Project Red only when a Codeforces individual accepted submission
is found between that session's start and finish, after submission sync. Codeforces
`time_consumed_ms` is execution time, not human solving time, and is never used
as a model input. The API uses the existing authenticated session and CSRF checks.

No additional public export API is needed for live recommendations: SAY performs
feature extraction and inference within the backend. Model retraining remains a
separate process and should not push identifiable user history to a public repository.
