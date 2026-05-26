"""add email tracks

Revision ID: 20260524_0003
Revises: 20260524_0002
Create Date: 2026-05-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260524_0003"
down_revision: Union[str, Sequence[str], None] = "20260524_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "manudocs_email_tracks",
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("tracking_token", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_manudocs_email_tracks_tracking_token",
        "manudocs_email_tracks",
        ["tracking_token"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_manudocs_email_tracks_tracking_token",
        table_name="manudocs_email_tracks",
    )
    op.drop_table("manudocs_email_tracks")
