"""SAY Flask application and database-management commands."""
import json
import os

import click
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import Flask
from flask_cors import CORS
from sqlalchemy import inspect

from config import Config
from database.db import db, migrate
from auth.routes import auth
from users.routes import users
from submissions.routes import submissions
from codeforces.routes import codeforces
from analytics.routes import analytics
from recommendations.routes import recommendations
from models.recommendation_log import RecommendationLog
from user_profile.routes import profile
from user_education.routes import education

# Alembic must see all ORM tables before migration autogeneration.
from models.users import User
from models.session import Session
from models.problem import Problem
from models.submission import Submission  # Local code files: unchanged.
from models.codeforces_account import CodeforcesAccount
from models.codeforces_submission import CodeforcesSubmission
from models.user_problem_progress import UserProblemProgress
from models.user_topic_mastery import UserTopicMastery, UserDifficultyReadiness
from models.recommendation_log import RecommendationLog
from models.user_profile import UserProfile
from models.user_education import UserEducation

from problem_stats.sync import sync_codeforces_problems
from codeforces.submission_sync import sync_codeforces_submissions
from codeforces.reconciliation import reconcile_unresolved_submissions
from analytics.progress import rebuild_user_progress, ProgressBuildError
from analytics.mastery import rebuild_user_skills, SkillEstimateError


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    secret = app.config.get("SECRET_KEY")
    if not secret or secret == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET":
        raise RuntimeError("Set a strong SECRET_KEY in .env before starting SAY")
    if int(app.config["SESSION_MAX_AGE_SECONDS"]) <= 0:
        raise RuntimeError("SESSION_MAX_AGE_SECONDS must be positive")
    origins = app.config.get("CORS_ORIGINS", [])
    if isinstance(origins, str):
        origins = [origin.strip() for origin in origins.split(",") if origin.strip()]
    if not origins or "*" in origins:
        raise RuntimeError("CORS_ORIGINS must explicitly list allowed frontend origins")

    CORS(
        app,
        resources={r"/*": {"origins": origins}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    db.init_app(app)
    migrate.init_app(app, db)
    # Never call db.create_all() at application startup: Alembic owns the schema.
    app.register_blueprint(auth)
    app.register_blueprint(users)
    app.register_blueprint(submissions)
    app.register_blueprint(codeforces)
    app.register_blueprint(analytics)
    app.register_blueprint(recommendations)
    app.register_blueprint(profile, url_prefix="/profile")
    app.register_blueprint(education, url_prefix="/education")
    


    @app.get("/")
    def health():
        return {"message": "SAY backend is running"}, 200

    @app.cli.command("sync-cf-problems")
    def sync_cf_problems_command():
        """Atomically update Codeforces problem metadata."""
        try:
            summary = sync_codeforces_problems()
        except Exception as exc:
            app.logger.exception("Codeforces problem sync failed")
            raise click.ClickException(f"Codeforces sync failed: {exc}") from exc
        click.echo(json.dumps(summary, indent=2))

    @app.cli.command("sync-cf-submissions")
    @click.option("--account-id", required=True, type=click.IntRange(min=1),
                  help="CodeforcesAccount.id, NOT the SAY user uid.")
    @click.option("--full", is_flag=True, help="Rescan all available submission history.")
    @click.option("--page-size", type=click.IntRange(1, 1000), default=500, show_default=True)
    @click.option("--overlap", type=click.IntRange(min=0), default=100,
                  show_default=True, help="Minimum known submissions before stopping incrementally.")
    @click.option("--lookback-days", type=click.IntRange(min=0), default=14,
                  show_default=True, help="Refresh recent verdicts within this window.")
    @click.option("--max-pages", type=click.IntRange(min=1), default=None,
                  help="Diagnostic cap; reaching it fails without advancing watermark.")
    def sync_cf_submissions_command(account_id, full, page_size, overlap, lookback_days, max_pages):
        """Import official Codeforces user.status data (long-running CLI job)."""
        try:
            result = sync_codeforces_submissions(
                account_id, full=full, page_size=page_size, overlap=overlap,
                lookback_days=lookback_days, max_pages=max_pages,
            )
        except Exception as exc:
            app.logger.exception("Codeforces submission import failed")
            raise click.ClickException(
                "Submission import failed; check logs and account sync_status"
            ) from exc
        click.echo(json.dumps(result, indent=2))

    @app.cli.command("reconcile-cf-submissions")
    @click.option("--account-id", required=True, type=click.IntRange(min=1))
    def reconcile_cf_submissions_command(account_id):
        """Match unresolved submissions to newly imported Codeforces problems."""
        try:
            count = reconcile_unresolved_submissions(account_id)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException("Reconciliation failed") from exc
        click.echo(f"Reconciled {count} problem references")

    @app.cli.command("rebuild-cf-progress")
    @click.option("--uid", required=True, type=click.IntRange(min=1),
                  help="SAY User.uid, NOT CodeforcesAccount.id.")
    def rebuild_cf_progress_command(uid):
        """Rebuild personal progress from active account official submissions."""
        try:
            summary = rebuild_user_progress(uid)
        except (ProgressBuildError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        except Exception as exc:
            app.logger.exception("User progress rebuild failed for uid=%s", uid)
            raise click.ClickException("Progress rebuild failed; check server logs") from exc
        click.echo(json.dumps(summary, indent=2))

    @app.cli.command("rebuild-cf-skills")
    @click.option("--uid", required=True, type=click.IntRange(min=1),
                  help="SAY User.uid, NOT CodeforcesAccount.id.")
    def rebuild_cf_skills_command(uid):
        """Recompute per-tag mastery and rating-band readiness from progress."""
        try:
            summary = rebuild_user_skills(uid)
        except (SkillEstimateError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        except Exception as exc:
            app.logger.exception("Skill rebuild failed for uid=%s", uid)
            raise click.ClickException("Skill rebuild failed; check server logs") from exc
        click.echo(json.dumps(summary, indent=2))

    @app.cli.command("grant-admin")
    @click.argument("username")
    def grant_admin(username):
        """Grant admin access via the trusted server shell."""
        user = User.query.filter_by(name=username).first()
        if user is None:
            raise click.ClickException("User not found")
        user.privilege = "admin"
        db.session.commit()
        click.echo(f"Admin privilege granted to {username}")

    @app.cli.command("db-info")
    def db_info():
        """Show database tables without disclosing credentials."""
        with db.engine.connect() as connection:
            tables = inspect(connection).get_table_names()
        click.echo(f"Dialect: {db.engine.dialect.name}")
        if db.engine.dialect.name == "sqlite":
            click.echo(f"SQLite file: {db.engine.url.database}")
        click.echo("Tables: " + (", ".join(sorted(tables)) or "(none)"))

    @app.cli.command("verify-db-schema")
    def verify_db_schema():
        """Compare the database schema against registered SQLAlchemy models."""
        expected = set(db.metadata.tables.keys())
        if not expected:
            raise click.ClickException("No model tables registered")
        with db.engine.connect() as connection:
            actual = set(inspect(connection).get_table_names())
            actual.discard("alembic_version")
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            if missing or extra:
                raise click.ClickException(
                    f"Schema mismatch. Missing tables: {missing}; extra tables: {extra}"
                )
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            differences = compare_metadata(context, db.metadata)
        if differences:
            for item in differences:
                click.echo(repr(item), err=True)
            raise click.ClickException("Schema differs from models; inspect differences")
        click.echo("Schema matches SQLAlchemy models according to Alembic autogenerate")
    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5001")),
        debug=app.config["DEBUG"],
    )
