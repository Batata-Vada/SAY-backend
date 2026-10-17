from database.db import db


class UserEducation(db.Model):
    __tablename__ = "user_education"

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    institution = db.Column(db.String(200), nullable=False)
    degree = db.Column(db.String(120), nullable=False)
    field_of_study = db.Column(db.String(160), nullable=True)
    start_year = db.Column(db.String(20), nullable=True)
    end_year = db.Column(db.String(20), nullable=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
