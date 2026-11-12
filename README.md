# SAY — Codeforces-only OIDC login, SAY profile, and problem forum

**Reviewed against GitHub**: `Batata-Vada/SAY-backend` `main` SHA `464467cae95266e7e75202362707407e7b253bc8` and `Batata-Vada/SAY-frontend` `main` SHA `07c9659a8d23b3ea842f0820fc0da5d5d443f6b7` on 2026-11-07.

## Critical architectural decision

- **Auth identity**: Codeforces OIDC ID token `iss + sub`, verified with HS256 and your app's client secret. Do NOT authenticate by Codeforces handle alone. Do NOT import Codeforces cookies or passwords.
- **Local identity**: existing `User.uid` remains the primary key used by progress, official submissions, skills, recommendations, profiles, forum threads, and replies.
- **Codeforces-only data**: verified Codeforces handle and **contest rating**. (Codeforces **problem rating** is a separate value on `Problem`, used by recommendations.) Codeforces avatar is ignored.
- **SAY-only data**: SAY username, display name, bio, uploaded avatar, social links, education, forums, votes, moderators and sessions.
- **History is not a forum permission**: users with incomplete/unavailable history can still ask questions. The viewer's own `UserProblemProgress.is_solved` determines default spoiler redaction; nobody else's history is exposed.
- **No frontend files were changed**. The current Next.js login page still uses password `/login`, `localStorage`, and the practice page uses mock `qid` values. The frontend team will need to integrate the OIDC browser redirect, same-site `credentials:'include'`, `X-SAY-CSRF`, and real canonical problem IDs.

Codeforces OIDC discovery: https://codeforces.com/.well-known/openid-configuration

Advertised endpoints: `https://codeforces.com/oauth/authorize` and `/oauth/token`; response_type `code`, scope `openid`, ID-token signing algorithm **HS256**, token client authentication **client_secret_post**. Codeforces announced OIDC in August 2025: https://codeforces.com/blog/entry/145566.

## 1. Prepare a branch and protect the database

```bash
cd "/home/sidhant/Projects/Batata Vada/SAY-backend"
source .venv/bin/activate
git status
git switch -c feat/codeforces-oidc-forum
flask --app main db-info
flask --app main db current
flask --app main db heads
```

Stop the Flask server and sync worker, and back up the SQLite DB **using the actual path from db-info**. With default `instance/app.db`, for example:

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
3. For local development, register the exact callback URI `http://localhost:5001/auth/codeforces/callback` **if permitted by Codeforces**. If localhost HTTP callbacks aren't accepted, use an HTTPS development origin and register that exact URI.
4. Obtain `client_id` and `client_secret` for that OAuth app. Keep the secret on the backend only.
5. Configure `.env` (never commit):

```dotenv
CODEFORCES_OIDC_CLIENT_ID=REPLACE_WITH_OAUTH_APP_ID
CODEFORCES_OIDC_CLIENT_SECRET=REPLACE_WITH_OAUTH_APP_SECRET
CODEFORCES_OIDC_REDIRECT_URI=http://localhost:5001/auth/codeforces/callback
SAY_FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000
SAY_COOKIE_SECURE=false
# Retain your existing strong SECRET_KEY and DATABASE_URL settings.
```

**Production:** use HTTPS for the frontend, callback, and backend; set `SAY_COOKIE_SECURE=true`; keep both on the same site, or coordinate changes to SameSite/CORS/CSRF protections with the frontend. The backend intentionally rejects insecure production OIDC callback configuration. The client secret must never reach the browser.

## 3. Extract the files and patch the current backend

Place the ZIP in the backend repo root. Inspect before overwriting:

```bash
unzip -l SAY_Codeforces_OIDC_SAY_Forum_Backend.zip
unzip -o SAY_Codeforces_OIDC_SAY_Forum_Backend.zip
python patches/apply_oidc_forum.py
```

The archive intentionally replaces these **legacy backend** files:

- `auth/routes.py`: `/register`, password `/login`, `/change-password` now return `410 Gone`; GET `/login` redirects to OIDC.
- `middleware/auth.py`: only OIDC-issued SAY sessions accepted; existing password sessions are invalid, and cookie-origin state changes require CSRF.
- `codeforces/routes.py`: account GET remains; `POST /api/codeforces/account` rejects manual handle linking.
- `users/routes.py`: retains SAY usernames/admin list but removes password changes and email disclosures.
- `models/users.py`, `models/session.py`, `models/user_profile.py`: schema updated for nullable legacy credentials, provider-tagged sessions, SAY avatars.

The patcher modifies existing `main.py`, `config.py`, and `user_profile/routes.py` without overwriting the newer profile/education/sync/recommender code. It enables credentialed CORS **only for your explicitly listed origins** and permits the `X-SAY-CSRF` preflight header. It can be run twice, but always inspect:

```bash
git diff -- main.py config.py user_profile/routes.py
python -m compileall -q main.py auth middleware forum say_profile users codeforces
```

New files include `auth/oidc.py`, `auth/oidc_tokens.py`, `models/codeforces_oidc_identity.py`, `models/forum.py`, `forum/routes.py`, `say_profile/routes.py`, `scripts/legacy_merge.py`, the migration, tests, and `.http` file.

## 4. Install only new dependencies

```bash
python -m pip install 'PyJWT==2.13.0' 'Pillow==12.3.0'
```

Also append these two pinned lines to your existing `requirements.txt` and commit it. Keep all existing requirements.

## 5. Apply Alembic migration

This migration has revision ID `e52a3f81bc90`, down revision `d39c6ab201e7` (current GitHub branch on inspection). It creates `codeforces_oidc_identities`, `oidc_login_states`, `forum_threads`, `forum_replies`, `forum_votes`, and adds `session.auth_provider`, `user_profiles.avatar_filename`, and nullable `user.email/password`.

```bash
flask --app main db current
flask --app main db heads
# If d39c6ab201e7 is your current applied revision and e52a3f81bc90 is the new head:
flask --app main db upgrade
flask --app main db current
flask --app main db check
flask --app main verify-db-schema
```

If your local history has other revisions, **reconcile migrations first**, do not edit down_revision blindly. Downgrading after new OIDC-only users exist is intentionally blocked rather than manufacturing legacy credentials.

## 6. Start the backend and sign in through Codeforces

```bash
python main.py
```

Open this URL in **a browser**:

`http://localhost:5001/auth/codeforces/login`

This creates a one-use state, redirects to Codeforces, returns to the registered callback, validates the HS256 ID token (`iss`, `aud`, signature, expiry, `sub` and optional `nonce`), creates/loads the user's SAY `uid`, binds the verified handle and contest rating, issues a new provider-tagged SAY session, and sets an **HttpOnly, SameSite=Lax** session cookie. The browser redirects to the configured SAY frontend URL with `?login=success` (the frontend must implement the post-login UI).

**Login is not testable by a simple username/password REST request.** The browser redirects and Codeforces authentication are required. Once signed in, REST Client can test the resulting session via a cookie copied into a private `.vscode/*.local.http` file.

### Sessions and CSRF

- Authentication cookie: `say_session`; backend sets `HttpOnly`, `SameSite=Lax`, `Secure` in HTTPS production.
- Frontend API fetches must use `credentials: 'include'` and `http://localhost:5001` to match the cookie site (not `127.0.0.1`).
- First call `GET /auth/csrf`, then include the returned `csrf_token` as `X-SAY-CSRF` for **POST/PUT/PATCH/DELETE** requests using cookie authentication.
- Existing bearer-token REST Client sessions are accepted **only if created by this verified OIDC flow**, not legacy password sessions. New browser login does not reveal the session cookie to JavaScript.
- `POST /auth/logout` revokes the stored session. `GET /auth/session` reports the current SAY user and Codeforces contest rating.

## 7. Sync and retain prior progress

Verified OIDC login creates a linked `CodeforcesAccount(ownership_verified=True)`, initially with `sync_status='PENDING'`; it does **not** import history synchronously during login.

Make sure the canonical Codeforces problem catalog has been imported (required for problem-linked forums and progress):

```bash
flask --app main sync-cf-problems
```

Use existing Step 9 `POST /api/codeforces/sync` and a separate worker:

```bash
flask --app main process-cf-sync-queue --limit 1
```

Then `GET /api/me/progress`, `/api/me/mastery`, and `GET /api/recommendations?limit=5&mode=new` continue working against the same `uid`.

### Very important: legacy accounts (e.g. former `sid_test`)

The old SAY username/password account has no cryptographic proof of which Codeforces person owns it. **Never automatically attach it to an OIDC identity merely because the stored handle matches.**

If you have a legacy user with historical data:

1. Complete Codeforces OIDC login as that Codeforces person. SAY will create a temporary new UID. Read it from `GET /auth/session`.
2. Do **not** sync, edit SAY profile, or publish forum content with the temporary account yet.
3. An administrator must **independently verify** that the old SAY account belongs to this person, compare the old active Codeforces handle to the newly verified handle, and back up the DB.
4. Stop writers/worker. If verification passes, run the operator-only CLI:

```bash
flask --app main adopt-legacy-oidc --legacy-uid 1 --verified-uid REPLACE_NEW_UID --confirm-reviewed-ownership
```

The helper refuses to merge if the temporary UID has progress, submissions, profiles, forum posts, or other meaningful user data. It transfers the **verified OIDC subject** to the old UID, preserves all data under that UID, removes the temporary empty account, and revokes its sessions. Sign in again via Codeforces. All prior data remains associated with the original `uid`.

If any preconditions fail, stop and plan a manual, reviewed data migration; don't delete one user's data to force a merge.

## 8. SAY-owned avatar and profile

`GET /api/me/say-profile` and `PATCH /api/me/say-profile` manage SAY display name/bio. `POST /api/me/avatar` accepts multipart `file` (PNG/JPEG/WEBP, <=2 MB), checks and recompresses it to max 512px WebP, stores under `instance/uploads/avatars`, and returns `/api/avatars/<uuid>.webp`.

Codeforces `avatar` claim is **intentionally ignored**. Back up avatar uploads separately from your database. For production multi-instance hosting, migrate uploads to trusted object storage/CDN and keep the URL under SAY's control.

Existing `/profile/me` and `/profile/<username>` continue working, with the patcher adding SAY avatar and display name fields to their output. Education remains in SAY's existing `user_education` table.

## 9. Canonical Codeforces problem forum

**Do not create one forum per user, or duplicate problem history in the forum database.**

```
User.uid --< CodeforcesOidcIdentity  (iss+sub, handle, contest rating)
    |---< CodeforcesAccount --< CodeforcesSubmission
    |---< UserProblemProgress >--- Problem.id
    |---< UserProfile (SAY avatar, name, bio)
    |---< ForumThread >--- Problem.id  (one problem can have many threads)
    |---< ForumReply >--- ForumThread.id
    `---< ForumVote >--- ForumThread.id
```

API (all require verified OIDC login):

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/problems/codeforces/1900/A` | Resolve CF contest+index to SAY `problem_id` |
| GET/POST | `/api/problems/<problem_id>/forum/threads` | List/create threads for canonical Codeforces problem |
| GET/PATCH/DELETE | `/api/forum/threads/<thread_id>` | Read/edit/soft-delete thread |
| GET/POST | `/api/forum/threads/<thread_id>/replies` | List/create replies; optional `parent_id` |
| PATCH/DELETE | `/api/forum/replies/<reply_id>` | Edit/soft-delete reply |
| PUT | `/api/forum/threads/<thread_id>/vote` | Upvote/downvote/remove (`1`, `-1`, `0`) |

Forum authors are always authenticated **SAY `uid`**, showing SAY display_name and SAY avatar only. No password/email/Codeforces avatar or another student's problem history is returned. Public Codeforces submissions are imported independently for progress; forum discussion doesn't modify them. Markdown should be rendered/sanitized safely by the frontend (never insert raw untrusted HTML).

Threads/replies support spoilers. By default, spoiler body text is hidden for viewers with no official `is_solved` progress for that problem (authors can see their own; viewers may deliberately reveal using `?reveal_spoilers=true`). This is a **UX spoiler filter**, not an access-control secret. Missing or stale history should not prevent questions. Rate limits, ownership checks, admin locks, and soft deletion are built in; add reporting/moderation dashboards and content policies before public launch.

**Frontend caveat:** current `lib/problems.ts` is a three-problem mock dataset with `qid` `1`, `2`, `3`; those are **not** Codeforces canonical identities. Frontend should eventually map contest ID and index using `/api/problems/codeforces/<contest>/<index>` and use returned SAY `problem_id` for forum APIs. No frontend files were touched in this package.

## 10. Tests and REST Client

```bash
python -m pytest tests/test_oidc_tokens.py tests/test_oidc_forum_patcher.py tests/test_oidc_forum_integration.py -v
flask --app main routes
```

The supplied `rest_client/codeforces_oidc_forum.http` works with Huachao Mao's VS Code REST Client. Store your real session cookie in a private Git-ignored `.vscode/oidc.local.http` copy:

```bash
mkdir -p .vscode
cp rest_client/codeforces_oidc_forum.http .vscode/oidc.local.http
```

Run browser login, copy the `say_session` cookie into the private file, send the CSRF request first, and then send forum/profile API requests. Never commit client secret, session cookie, or temporary OIDC authorization code.

## 11. Commit only reviewed files

```bash
git status
git diff --check
git add auth/oidc.py auth/oidc_tokens.py auth/routes.py middleware/auth.py
# Also stage all other reviewed backend sources, migrations, README and REST Client file.
git add main.py config.py users/routes.py codeforces/routes.py user_profile/routes.py
git add models/ forum/ say_profile/ scripts/ patches/apply_oidc_forum.py

git add migrations/versions/e52a3f81bc90_add_oidc_identity_and_problem_forum.py
git add rest_client/codeforces_oidc_forum.http
# Add tests explicitly: your repo ignores /tests
git add -f tests/test_oidc_tokens.py tests/test_oidc_forum_patcher.py tests/test_oidc_forum_integration.py
git status
git commit -m "feat: use Codeforces OIDC identity and add SAY problem forum"
git push -u origin HEAD
```

**Security/operational notes:** Codeforces's current issuer advertises HS256, not RS256/JWKS. Never disable signature/audience/issuer verification. Treat the `sub` as the identity; Codeforces handles can change. Prefer stable canonical `Problem.id` for forum FK and `User.uid` for author FK. Back up both DB and avatar files, enforce HTTPS and secure cookies in production, and add stronger persistent multi-process forum abuse rate limiting (e.g. Redis) before exposure to the wider internet.
