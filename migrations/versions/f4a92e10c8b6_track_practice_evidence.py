"""Track Codeforces evidence availability and practice recommendation provenance."""
from alembic import op
import sqlalchemy as sa

revision = "f4a92e10c8b6"
down_revision = "6cc8b115d15a"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("codeforces_submissions") as batch:
        batch.add_column(sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("final_verdict_observed_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("codeforces_accounts") as batch:
        batch.add_column(sa.Column("last_full_sync_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("practice_sessions") as batch:
        batch.add_column(sa.Column("recommendation_run_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_practice_recommendation_run", ["recommendation_run_id"])


def downgrade():
    with op.batch_alter_table("practice_sessions") as batch:
        batch.drop_index("ix_practice_recommendation_run")
        batch.drop_column("recommendation_run_id")
    with op.batch_alter_table("codeforces_accounts") as batch:
        batch.drop_column("last_full_sync_at")
    with op.batch_alter_table("codeforces_submissions") as batch:
        batch.drop_column("final_verdict_observed_at")
        batch.drop_column("first_observed_at")
