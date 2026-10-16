"""SAY Flask application."""

import os
import click

from flask import Flask
from flask_cors import CORS

from config import Config
from database.db import db

from auth.routes import auth
from users.routes import users
from submissions.routes import submissions

# Import ORM models before creating tables.
from models.users import User
from models.session import Session
from models.problem import Problem
from models.submission import Submission

from problem_stats.sync import sync_all


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    secret = app.config.get("SECRET_KEY")

    if (
        not secret
        or secret == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    ):
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
            "CORS_ORIGINS must explicitly list "
            "allowed frontend origins"
        )

    CORS(
        app,
        resources={
            r"/*": {"origins": origins}
        },
        supports_credentials=False,
        allow_headers=[
            "Content-Type",
            "Authorization"
        ],
        methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS"
        ]
    )

    db.init_app(app)

    app.register_blueprint(auth)
    app.register_blueprint(users)
    app.register_blueprint(submissions)

    # Temporary compatibility for Step 1.
    # Replace with Flask-Migrate in Step 2.
    with app.app_context():
        db.create_all()

    @app.get("/")
    def health():
        return {
            "message": "SAY backend is running"
        }, 200

    @app.cli.command("sync-problems")
    def sync_problems_command():
        """Sync existing problem collectors."""
        click.echo(sync_all())

    @app.cli.command("grant-admin")
    @click.argument("username")
    def grant_admin(username):
        """Grant admin privilege from the server CLI."""

        user = User.query.filter_by(
            name=username
        ).first()

        if user is None:
            raise click.ClickException("User not found")

        user.privilege = "admin"
        db.session.commit()

        click.echo(
            f"Admin privilege granted to {username}"
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5001")),
        debug=app.config["DEBUG"]
    )