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
