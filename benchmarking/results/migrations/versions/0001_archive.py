"""Create the initial archive. Future schema changes require a new revision."""

from alembic import op

from benchmarking.results.schema import metadata

revision = "0001_archive"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
