from alembic import op
import sqlalchemy as sa

revision = "f38b1c240a21"
down_revision = "e52a3f81bc90"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("codeforces_accounts") as batch:
        batch.add_column(sa.Column("current_rating", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rated_contests", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rating_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.Integer(), sa.ForeignKey("user.uid"), nullable=False),
        sa.Column("source_account_id", sa.Integer(), sa.ForeignKey("codeforces_accounts.id"), nullable=False),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0", name="ck_practice_duration_positive"),
    )
    op.create_index("ix_practice_sessions_uid", "practice_sessions", ["uid"])
    op.create_index("ix_practice_sessions_source_account_id", "practice_sessions", ["source_account_id"])
    op.create_index("ix_practice_sessions_problem_id", "practice_sessions", ["problem_id"])
    op.create_index("ix_practice_user_status", "practice_sessions", ["uid", "status"])


def downgrade():
    op.drop_index("ix_practice_user_status", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_problem_id", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_source_account_id", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_uid", table_name="practice_sessions")
    op.drop_table("practice_sessions")
    with op.batch_alter_table("codeforces_accounts") as batch:
        batch.drop_column("rating_updated_at")
        batch.drop_column("rated_contests")
        batch.drop_column("current_rating")
