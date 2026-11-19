"""Problem-anchored SAY forum; author uid is SAY identity, never a CF handle."""
from datetime import datetime, timezone
from database.db import db


def utcnow():
    return datetime.now(timezone.utc)


class ForumThread(db.Model):
    __tablename__ = 'forum_threads'
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('problems.id'), nullable=False, index=True)
    author_uid = db.Column(db.Integer, db.ForeignKey('user.uid'), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    spoiler = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    is_locked = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (db.Index('ix_forum_threads_problem_created','problem_id','created_at'),)


class ForumReply(db.Model):
    __tablename__ = 'forum_replies'
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('forum_threads.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('forum_replies.id'), nullable=True)
    author_uid = db.Column(db.Integer, db.ForeignKey('user.uid'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    spoiler = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (db.Index('ix_forum_replies_thread_created','thread_id','created_at'),)


class ForumVote(db.Model):
    """One vote per uid per thread; no fake identity or platform submissions."""
    __tablename__ = 'forum_votes'
    uid = db.Column(db.Integer, db.ForeignKey('user.uid'), primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('forum_threads.id'), primary_key=True)
    value = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.CheckConstraint('value IN (-1, 1)', name='ck_forum_vote_value'),)
