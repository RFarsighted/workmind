"""create ERP application history

Revision ID: 20261007_0003
Revises: 20261006_0002
Create Date: 2026-10-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261007_0003"
down_revision: Union[str, None] = "20261006_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "erp_applications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("form_type", sa.String(length=16), nullable=False),
        sa.Column("applicant_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("form_data", sa.JSON(), nullable=False),
        sa.Column("approval_steps", sa.JSON(), nullable=False),
        sa.Column("approval_messages", sa.JSON(), nullable=False),
        sa.Column("final_result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_erp_applications_form_type", "erp_applications", ["form_type"])
    op.create_index("ix_erp_applications_status", "erp_applications", ["status"])
    op.create_index("ix_erp_applications_created_at", "erp_applications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_erp_applications_created_at", table_name="erp_applications")
    op.drop_index("ix_erp_applications_status", table_name="erp_applications")
    op.drop_index("ix_erp_applications_form_type", table_name="erp_applications")
    op.drop_table("erp_applications")
