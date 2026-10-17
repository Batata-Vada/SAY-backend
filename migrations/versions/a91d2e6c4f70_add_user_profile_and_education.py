"""Add user profile and education tables."""
from alembic import op
import sqlalchemy as sa

revision = "a91d2e6c4f70"
down_revision = "62cf427593c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.Integer(), sa.ForeignKey("user.uid", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("instagram_url", sa.String(length=500), nullable=True),
        sa.Column("x_url", sa.String(length=500), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("leetcode_url", sa.String(length=500), nullable=True),
        sa.Column("codeforces_url", sa.String(length=500), nullable=True),
        sa.Column("codechef_url", sa.String(length=500), nullable=True),
        sa.Column("show_instagram", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_x", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_linkedin", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_leetcode", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_codeforces", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_codechef", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_user_profile_uid", "user_profile", ["uid"], unique=False)

    op.create_table(
        "user_education",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.Integer(), sa.ForeignKey("user.uid", ondelete="CASCADE"), nullable=False),
        sa.Column("institution", sa.String(length=200), nullable=False),
        sa.Column("degree", sa.String(length=120), nullable=False),
        sa.Column("field_of_study", sa.String(length=160), nullable=True),
        sa.Column("start_year", sa.String(length=20), nullable=True),
        sa.Column("end_year", sa.String(length=20), nullable=True),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_user_education_uid", "user_education", ["uid"], unique=False)


def downgrade():
    op.drop_index("ix_user_education_uid", table_name="user_education")
    op.drop_table("user_education")
    op.drop_index("ix_user_profile_uid", table_name="user_profile")
    op.drop_table("user_profile")
