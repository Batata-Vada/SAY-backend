"""Codeforces OIDC identities, SAY avatars, per-problem forum.

Revision ID: e52a3f81bc90
Revises: d39c6ab201e7
Only use when local Alembic head matches the revision chain.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e52a3f81bc90'
down_revision = 'd39c6ab201e7'
branch_labels = None
depends_on = None


def upgrade():
    # Existing users and FKs remain; new OIDC users do not need legacy credentials.
    with op.batch_alter_table('user') as batch:
        batch.alter_column('email', existing_type=sa.String(length=120), nullable=True)
        batch.alter_column('password', existing_type=sa.String(length=255), nullable=True)
    with op.batch_alter_table('session') as batch:
        batch.add_column(sa.Column('auth_provider', sa.String(length=32), nullable=True))
    with op.batch_alter_table('user_profiles') as batch:
        batch.add_column(sa.Column('avatar_filename', sa.String(length=64), nullable=True))

    op.create_table('codeforces_oidc_identities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('uid', sa.Integer(), nullable=False),
        sa.Column('issuer', sa.String(length=128), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('handle', sa.String(length=64), nullable=False),
        sa.Column('contest_rating', sa.Integer(), nullable=True),
        sa.Column('rating_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['uid'],['user.uid']),
        sa.UniqueConstraint('issuer','subject',name='uq_cf_oidc_issuer_subject'),
    )
    op.create_index('ix_codeforces_oidc_identities_uid','codeforces_oidc_identities',['uid'],unique=True)
    op.create_table('oidc_login_states',
        sa.Column('state_digest',sa.String(length=64),primary_key=True),
        sa.Column('nonce',sa.String(length=128),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('used_at',sa.DateTime(timezone=True),nullable=True),
    )
    op.create_table('forum_threads',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('problem_id',sa.Integer(),nullable=False),
        sa.Column('author_uid',sa.Integer(),nullable=False),
        sa.Column('title',sa.String(length=160),nullable=False),
        sa.Column('body',sa.Text(),nullable=False),
        sa.Column('spoiler',sa.Boolean(),nullable=False),
        sa.Column('is_deleted',sa.Boolean(),nullable=False),
        sa.Column('is_locked',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['problem_id'],['problems.id']),
        sa.ForeignKeyConstraint(['author_uid'],['user.uid']),
    )
    op.create_index('ix_forum_threads_problem_id','forum_threads',['problem_id'])
    op.create_index('ix_forum_threads_author_uid','forum_threads',['author_uid'])
    op.create_index('ix_forum_threads_problem_created','forum_threads',['problem_id','created_at'])
    op.create_table('forum_replies',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('thread_id',sa.Integer(),nullable=False),
        sa.Column('parent_id',sa.Integer(),nullable=True),
        sa.Column('author_uid',sa.Integer(),nullable=False),
        sa.Column('body',sa.Text(),nullable=False),
        sa.Column('spoiler',sa.Boolean(),nullable=False),
        sa.Column('is_deleted',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['thread_id'],['forum_threads.id']),
        sa.ForeignKeyConstraint(['parent_id'],['forum_replies.id']),
        sa.ForeignKeyConstraint(['author_uid'],['user.uid']),
    )
    op.create_index('ix_forum_replies_thread_id','forum_replies',['thread_id'])
    op.create_index('ix_forum_replies_author_uid','forum_replies',['author_uid'])
    op.create_index('ix_forum_replies_thread_created','forum_replies',['thread_id','created_at'])
    op.create_table('forum_votes',
        sa.Column('uid',sa.Integer(),nullable=False),
        sa.Column('thread_id',sa.Integer(),nullable=False),
        sa.Column('value',sa.Integer(),nullable=False),
        sa.ForeignKeyConstraint(['uid'],['user.uid']),
        sa.ForeignKeyConstraint(['thread_id'],['forum_threads.id']),
        sa.PrimaryKeyConstraint('uid','thread_id'),
        sa.CheckConstraint('value IN (-1, 1)',name='ck_forum_vote_value'),
    )


def downgrade():
    # A legacy password schema cannot represent Codeforces-only user accounts.
    null_users=op.get_bind().execute(sa.text("SELECT count(*) FROM user WHERE email IS NULL OR password IS NULL")).scalar_one()
    if null_users:
        raise RuntimeError('Cannot downgrade while Codeforces-only users have NULL legacy credentials; preserve a database backup and plan manual conversion')
    op.drop_table('forum_votes')
    op.drop_index('ix_forum_replies_thread_created',table_name='forum_replies')
    op.drop_index('ix_forum_replies_author_uid',table_name='forum_replies')
    op.drop_index('ix_forum_replies_thread_id',table_name='forum_replies')
    op.drop_table('forum_replies')
    op.drop_index('ix_forum_threads_problem_created',table_name='forum_threads')
    op.drop_index('ix_forum_threads_author_uid',table_name='forum_threads')
    op.drop_index('ix_forum_threads_problem_id',table_name='forum_threads')
    op.drop_table('forum_threads')
    op.drop_table('oidc_login_states')
    op.drop_index('ix_codeforces_oidc_identities_uid',table_name='codeforces_oidc_identities')
    op.drop_table('codeforces_oidc_identities')
    with op.batch_alter_table('user_profiles') as batch:
        batch.drop_column('avatar_filename')
    with op.batch_alter_table('session') as batch:
        batch.drop_column('auth_provider')
    with op.batch_alter_table('user') as batch:
        batch.alter_column('email', existing_type=sa.String(length=120), nullable=False)
        batch.alter_column('password', existing_type=sa.String(length=255), nullable=False)
