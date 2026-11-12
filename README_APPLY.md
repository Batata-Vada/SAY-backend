# SAY backend — warning and repository cleanup

These five files were based on `Batata-Vada/SAY-backend` `main` at GitHub SHA `48ead1dbd64bc40b7e77cdc955dbd33a1f30846b` (2026-11-12).

## What's changed

- `models/user_profile.py`, `models/user_education.py`: replace deprecated `datetime.utcnow` defaults with `datetime.now(timezone.utc).replace(tzinfo=None)` for backward-compatible UTC-naive SQLite values. **No schema changes or migration required.**
- `config.py`: remove the repeated `RECOMMENDATION_WEIGHTS`, `RECOMMENDATION_DEFAULT_RATING`, `RECOMMENDATION_CANDIDATE_POOL_CAP` definitions without changing values.
- `requirements.txt`: include `PyJWT==2.13.0` and `Pillow==12.3.0`, already listed in `requirements_STEP_OIDC.txt`.
- `.gitignore`: make `/tests` trackable; continue ignoring `.venv`, `.env`, local databases, `.vscode`, and private REST Client files.

## Apply safely in WSL

From the SAY backend root, after reviewing the ZIP contents and committing or stashing any **local modifications to these same files**:

```bash
unzip -l SAY_backend_warning_cleanup.zip
unzip -o SAY_backend_warning_cleanup.zip
python -m pip install -r requirements.txt
python -m compileall -q models/user_profile.py models/user_education.py config.py
python -m pytest -v
flask --app main db check
flask --app main verify-db-schema
git diff --check
git diff -- models/user_profile.py models/user_education.py config.py requirements.txt .gitignore
```

To commit tests (whose files were previously ignored):

```bash
git add models/user_profile.py models/user_education.py config.py requirements.txt .gitignore
# Only after reviewing test files for secrets:
git add tests/
git commit -m "fix: replace deprecated UTC defaults and clean backend config"
```

**Note:** The ZIP is meant to extract *directly into the repository root*. Do not copy it over uncommitted changes without comparing files. The changes do not remove previously emitted warnings from older test runs; rerun pytest to verify.
