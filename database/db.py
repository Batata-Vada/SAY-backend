"""Shared database and migration extensions for SAY."""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Initialized once in create_app().
# Models continue importing `db` from here.
db = SQLAlchemy()
migrate = Migrate()