"""Durable Codeforces sync request queue.

Revision ID: d39c6ab201e7
Revises: af3eacc533a2
"""
from alembic import op
import sqlalchemy as sa

revision = "d39c6ab201e7"
down_revision = "af3eacc533a2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "codeforces_sync_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("codeforces_account_id", sa.Integer(), nullable=False),
        sa.Column("full", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_raw", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["uid"], ["user.uid"]),
        sa.ForeignKeyConstraint(["codeforces_account_id"], ["codeforces_accounts.id"]),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_cf_sync_requests_status",
        ),
    )
    op.create_index("ix_codeforces_sync_requests_uid", "codeforces_sync_requests", ["uid"])
    op.create_index("ix_codeforces_sync_requests_codeforces_account_id", "codeforces_sync_requests", ["codeforces_account_id"])
    op.create_index("ix_cf_sync_requests_account_requested", "codeforces_sync_requests",
                    ["codeforces_account_id", "requested_at"])
    op.create_index("uq_cf_sync_requests_open_account", "codeforces_sync_requests",
                    ["codeforces_account_id"], unique=True,
                    sqlite_where=sa.text("status IN ('QUEUED','RUNNING')"),
                    postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"))


def downgrade():
    op.drop_index("uq_cf_sync_requests_open_account", table_name="codeforces_sync_requests")
    op.drop_index("ix_cf_sync_requests_account_requested", table_name="codeforces_sync_requests")
    op.drop_index("ix_codeforces_sync_requests_codeforces_account_id", table_name="codeforces_sync_requests")
    op.drop_index("ix_codeforces_sync_requests_uid", table_name="codeforces_sync_requests")
    op.drop_table("codeforces_sync_requests")
