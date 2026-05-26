"""add email templates

Revision ID: 20260524_0002
Revises: 20260524_0001
Create Date: 2026-05-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260524_0002"
down_revision: Union[str, Sequence[str], None] = "20260524_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


email_templates_table = sa.table(
    "manudocs_email_templates",
    sa.column("name", sa.String()),
    sa.column("use_case", sa.String()),
    sa.column("subject", sa.String()),
    sa.column("html_template", sa.String()),
    sa.column("text_template", sa.String()),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "manudocs_email_templates",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("use_case", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("html_template", sa.String(), nullable=False),
        sa.Column("text_template", sa.String(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("use_case"),
    )
    op.bulk_insert(
        email_templates_table,
        [
            {
                "name": "Login code",
                "use_case": "login",
                "subject": "Your ManuDocs login code",
                "html_template": """
<p>Your ManuDocs login code is <strong>{{ otp }}</strong>.</p>
<p>This code expires soon. If you did not request it, you can ignore this email.</p>
""".strip(),
                "text_template": """
Your ManuDocs login code is {{ otp }}.

This code expires soon. If you did not request it, you can ignore this email.
""".strip(),
            }
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("manudocs_email_templates")
