"""Add append-only recommendation logs.

Revision ID: c8a7d410f26b
Revises: b4e19c7ad203
"""
from alembic import op
import sqlalchemy as sa

revision = "c8a7d410f26b"
down_revision = "b4e19c7ad203"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recommendation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=True),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("request_mode", sa.String(length=16), nullable=False),
        sa.Column("candidate_type", sa.String(length=16), nullable=False),
        sa.Column("profile_strategy", sa.String(length=24), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("target_rating", sa.Integer(), nullable=False),
        sa.Column("ranking_strategy", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_components", sa.JSON(), nullable=False),
        sa.Column("scoring_weights", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid"], ["user.uid"]),
        sa.ForeignKeyConstraint(["source_account_id"], ["codeforces_accounts.id"]),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"]),
        sa.UniqueConstraint("run_id", "rank", name="uq_recommendation_run_rank"),
    )
    op.create_index("ix_recommendation_logs_run_id", "recommendation_logs", ["run_id"])
    op.create_index("ix_recommendation_logs_uid", "recommendation_logs", ["uid"])
    op.create_index("ix_recommendation_logs_uid_created", "recommendation_logs", ["uid", "created_at"])


def downgrade():
    op.drop_index("ix_recommendation_logs_uid_created", table_name="recommendation_logs")
    op.drop_index("ix_recommendation_logs_uid", table_name="recommendation_logs")
    op.drop_index("ix_recommendation_logs_run_id", table_name="recommendation_logs")
    op.drop_table("recommendation_logs")
