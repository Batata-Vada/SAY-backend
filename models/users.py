"""SAY-local user key. Codeforces OIDC identity is held in separate identity table."""
from database.db import db

class User(db.Model):
    __tablename__ = 'user'
    uid = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)  # SAY-only handle
    email = db.Column(db.String(120), unique=True, nullable=True)  # legacy; never populated by OIDC
    password = db.Column(db.String(255), nullable=True)  # legacy; no usable password login
    privilege = db.Column(db.String(20), nullable=False, default='user')
