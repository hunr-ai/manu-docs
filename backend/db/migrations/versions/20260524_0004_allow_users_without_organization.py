"""allow users without organization

Revision ID: 20260524_0004
Revises: 20260524_0003
Create Date: 2026-05-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260524_0004"
down_revision: Union[str, Sequence[str], None] = "20260524_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "manudocs_users",
        "organization_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "manudocs_users",
        "organization_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
