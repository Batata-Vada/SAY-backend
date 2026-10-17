from datetime import datetime

from database.db import db


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.uid", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    display_name = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)

    instagram_url = db.Column(db.String(255), nullable=True)
    x_url = db.Column(db.String(255), nullable=True)
    linkedin_url = db.Column(db.String(255), nullable=True)
    leetcode_url = db.Column(db.String(255), nullable=True)
    codeforces_url = db.Column(db.String(255), nullable=True)
    codechef_url = db.Column(db.String(255), nullable=True)

    show_instagram = db.Column(db.Boolean, nullable=False, default=True)
    show_x = db.Column(db.Boolean, nullable=False, default=True)
    show_linkedin = db.Column(db.Boolean, nullable=False, default=True)
    show_leetcode = db.Column(db.Boolean, nullable=False, default=True)
    show_codeforces = db.Column(db.Boolean, nullable=False, default=True)
    show_codechef = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )