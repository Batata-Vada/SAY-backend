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

# All models must be imported for Alembic to detect their tables.
from models.users import User
from models.session import Session
from models.problem import Problem
from models.submission import Submission

from problem_stats.sync import sync_codeforces_problems


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    secret = app.config.get("SECRET_KEY")
    if not secret or secret == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET":
        raise RuntimeError(
            "Set a strong SECRET_KEY in .env before starting SAY"
        )

    if int(app.config["SESSION_MAX_AGE_SECONDS"]) <= 0:
        raise RuntimeError(
            "SESSION_MAX_AGE_SECONDS must be positive"
        )

    origins = app.config.get("CORS_ORIGINS", [])
    if isinstance(origins, str):
        origins = [
            origin.strip()
            for origin in origins.split(",")
            if origin.strip()
        ]

    if not origins or "*" in origins:
        raise RuntimeError(
            "CORS_ORIGINS must explicitly list allowed frontend origins"
        )

    CORS(
        app,
        resources={r"/*": {"origins": origins}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        methods=[
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
        ],
    )

    db.init_app(app)
    migrate.init_app(app, db)

    # IMPORTANT: No db.create_all(); Step 2 migrations own the schema.
    app.register_blueprint(auth)
    app.register_blueprint(users)
    app.register_blueprint(submissions)

    @app.get("/")
    def health():
        return {"message": "SAY backend is running"}, 200

    @app.cli.command("sync-cf-problems")
    def sync_cf_problems_command():
        """Atomically download/update Codeforces problem metadata."""
        try:
            summary = sync_codeforces_problems()
        except Exception as exc:
            app.logger.exception("Codeforces problem sync failed")
            raise click.ClickException(
                f"Codeforces sync failed: {exc}"
            ) from exc
        click.echo(json.dumps(summary, indent=2))

    @app.cli.command("grant-admin")
    @click.argument("username")
    def grant_admin(username):
        """Grant admin privilege through the server CLI."""
        user = User.query.filter_by(name=username).first()
        if user is None:
            raise click.ClickException("User not found")
        user.privilege = "admin"
        db.session.commit()
        click.echo(f"Admin privilege granted to {username}")

    @app.cli.command("db-info")
    def db_info():
        """Display database information without credentials."""
        with db.engine.connect() as connection:
            table_names = inspect(connection).get_table_names()

        click.echo(f"Dialect: {db.engine.dialect.name}")
        if db.engine.dialect.name == "sqlite":
            click.echo(f"SQLite file: {db.engine.url.database}")
        click.echo(
            "Tables: " + (", ".join(sorted(table_names)) or "(none)")
        )

    @app.cli.command("verify-db-schema")
    def verify_db_schema():
        """Compare the existing DB with imported ORM models."""
        expected_tables = set(db.metadata.tables.keys())
        if not expected_tables:
            raise click.ClickException(
                "No model tables registered; check model imports in main.py"
            )

        with db.engine.connect() as connection:
            actual_tables = set(inspect(connection).get_table_names())
            actual_tables.discard("alembic_version")
            missing = sorted(expected_tables - actual_tables)
            extra = sorted(actual_tables - expected_tables)
            if missing or extra:
                raise click.ClickException(
                    f"Schema mismatch. Missing tables: {missing}; "
                    f"unexpected tables: {extra}. Do not stamp this database."
                )

            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True},
            )
            differences = compare_metadata(context, db.metadata)

        if differences:
            for change in differences:
                click.echo(repr(change), err=True)
            raise click.ClickException(
                "Schema differs from models. Do not stamp this database. "
                "Inspect these differences first."
            )

        click.echo(
            "Schema matches imported SQLAlchemy models according to "
            "Alembic autogenerate. Review important constraints before stamping."
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5001")),
        debug=app.config["DEBUG"],
    )