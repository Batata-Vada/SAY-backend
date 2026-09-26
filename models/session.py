from database.db import db

class Session(db.Model):

    sid = db.Column(db.Integer, primary_key=True)

    uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid"),
        nullable=False
    )

    token = db.Column(
        db.String(255),
        unique=True,
        nullable=False
    )