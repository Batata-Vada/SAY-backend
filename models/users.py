from database.db import db


class User(db.Model):

    uid = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    privilege = db.Column(
        db.String(20),
        nullable=False,
        default="user"
    )