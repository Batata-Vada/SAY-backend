from database.db import db


class UserProfile(db.Model):
    __tablename__ = "user_profile"

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    instagram_url = db.Column(db.String(500), nullable=True)
    x_url = db.Column(db.String(500), nullable=True)
    linkedin_url = db.Column(db.String(500), nullable=True)
    leetcode_url = db.Column(db.String(500), nullable=True)
    codeforces_url = db.Column(db.String(500), nullable=True)
    codechef_url = db.Column(db.String(500), nullable=True)

    show_instagram = db.Column(db.Boolean, nullable=False, default=True)
    show_x = db.Column(db.Boolean, nullable=False, default=True)
    show_linkedin = db.Column(db.Boolean, nullable=False, default=True)
    show_leetcode = db.Column(db.Boolean, nullable=False, default=True)
    show_codeforces = db.Column(db.Boolean, nullable=False, default=True)
    show_codechef = db.Column(db.Boolean, nullable=False, default=True)
