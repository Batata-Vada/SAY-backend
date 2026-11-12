"""Verified external identity, deliberately separate from SAY-owned profile data."""
from datetime import datetime, timezone
from database.db import db


def utcnow():
    return datetime.now(timezone.utc)


class CodeforcesOidcIdentity(db.Model):
    __tablename__ = 'codeforces_oidc_identities'
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.Integer, db.ForeignKey('user.uid'), nullable=False, unique=True, index=True)
    issuer = db.Column(db.String(128), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    handle = db.Column(db.String(64), nullable=False)
    contest_rating = db.Column(db.Integer, nullable=True)
    rating_updated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint('issuer','subject',name='uq_cf_oidc_issuer_subject'),)

    def public(self):
        return {'handle':self.handle,'rating':self.contest_rating,'rating_updated_at':self.rating_updated_at.isoformat() if self.rating_updated_at else None,
                'rating_type':'codeforces_contest_rating'}


class OidcLoginState(db.Model):
    __tablename__ = 'oidc_login_states'
    state_digest = db.Column(db.String(64), primary_key=True)
    nonce = db.Column(db.String(128), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
