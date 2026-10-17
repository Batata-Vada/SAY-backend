"""Add materialized Codeforces topic mastery and difficulty readiness.

Revision ID: b4e19c7ad203
Revises: 703dc06d9251

This revision is based on SAY-backend/main at 2026-10-17.
Check your local Alembic head before using it. Do not autogenerate an
additional revision for the same tables.
"""

from alembic import op
import sqlalchemy as sa

revision = "b4e19c7ad203"
down_revision = "703dc06d9251"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_topic_mastery",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=128), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=False),
        sa.Column("attempted_problems", sa.Integer(), nullable=False),
        sa.Column("solved_problems", sa.Integer(), nullable=False),
        sa.Column("decided_problems", sa.Integer(), nullable=False),
        sa.Column("rated_decided_problems", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=True),
        sa.Column("smoothed_success_rate", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("mean_rated_difficulty", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid"], ["user.uid"]),
        sa.ForeignKeyConstraint(["source_account_id"], ["codeforces_accounts.id"]),
        sa.PrimaryKeyConstraint("uid", "tag"),
        sa.CheckConstraint(
            "attempted_problems >= 0 AND solved_problems >= 0 "
            "AND solved_problems <= attempted_problems "
            "AND decided_problems >= 0 AND decided_problems <= attempted_problems "
            "AND rated_decided_problems >= 0 "
            "AND rated_decided_problems <= decided_problems",
            name="ck_user_topic_mastery_counts",
        ),
    )
    op.create_index(
        "ix_user_topic_mastery_source_account_id", "user_topic_mastery",
        ["source_account_id"], unique=False,
    )
    op.create_index(
        "ix_user_topic_mastery_uid_score", "user_topic_mastery",
        ["uid", "mastery_score"], unique=False,
    )

    op.create_table(
        "user_difficulty_readiness",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=False),
        sa.Column("readiness_rating", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rated_attempted_problems", sa.Integer(), nullable=False),
        sa.Column("rated_decided_problems", sa.Integer(), nullable=False),
        sa.Column("rated_solved_problems", sa.Integer(), nullable=False),
        sa.Column("rating_bands_raw", sa.JSON(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid"], ["user.uid"]),
        sa.ForeignKeyConstraint(["source_account_id"], ["codeforces_accounts.id"]),
        sa.PrimaryKeyConstraint("uid"),
        sa.CheckConstraint(
            "rated_attempted_problems >= 0 AND rated_decided_problems >= 0 "
            "AND rated_decided_problems <= rated_attempted_problems "
            "AND rated_solved_problems >= 0 "
            "AND rated_solved_problems <= rated_decided_problems",
            name="ck_user_difficulty_readiness_counts",
        ),
    )
    op.create_index(
        "ix_user_difficulty_readiness_source_account_id",
        "user_difficulty_readiness", ["source_account_id"], unique=False,
    )


def downgrade():
    op.drop_index("ix_user_difficulty_readiness_source_account_id",
                  table_name="user_difficulty_readiness")
    op.drop_table("user_difficulty_readiness")
    op.drop_index("ix_user_topic_mastery_uid_score", table_name="user_topic_mastery")
    op.drop_index("ix_user_topic_mastery_source_account_id", table_name="user_topic_mastery")
    op.drop_table("user_topic_mastery")
