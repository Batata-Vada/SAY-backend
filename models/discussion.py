from datetime import datetime, timezone

from sqlalchemy import and_
from database.db import db


def utcnow():
    return datetime.now(timezone.utc)


class DiscussionPost(db.Model):
    __tablename__ = "discussion_posts"

    id = db.Column(db.Integer, primary_key=True)

    author_uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid"),
        nullable=False,
        index=True
    )

    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)

    category = db.Column(
        db.String(32),
        nullable=False,
        default="GENERAL",
        index=True
    )

    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    is_locked = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow
    )

    replies = db.relationship(
        "DiscussionReply",
        primaryjoin=lambda: and_(
            DiscussionPost.id == DiscussionReply.post_id,
            DiscussionReply.parent_id.is_(None)
        ),
        foreign_keys=lambda: [DiscussionReply.post_id],
        viewonly=True,
        order_by=lambda: [
            DiscussionReply.created_at,
            DiscussionReply.id
        ]
    )

    __table_args__ = (
        db.Index(
            "ix_discussion_posts_created",
            "created_at",
            "id"
        ),
    )


class DiscussionReply(db.Model):
    __tablename__ = "discussion_replies"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("discussion_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # NULL means a direct reply to a post.
    # Otherwise, this references another reply.
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("discussion_replies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    author_uid = db.Column(
        db.Integer,
        db.ForeignKey("user.uid"),
        nullable=False,
        index=True
    )

    body = db.Column(db.Text, nullable=False)

    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow
    )

    post = db.relationship(
        "DiscussionPost",
        foreign_keys=[post_id]
    )

    parent_reply = db.relationship(
        "DiscussionReply",
        remote_side=[id],
        foreign_keys=[parent_id],
        back_populates="replies"
    )

    replies = db.relationship(
        "DiscussionReply",
        foreign_keys=[parent_id],
        back_populates="parent_reply",
        order_by=lambda: [
            DiscussionReply.created_at,
            DiscussionReply.id
        ]
    )

    __table_args__ = (
        db.Index(
            "ix_discussion_replies_post_created",
            "post_id",
            "created_at"
        ),
    )