"""add prompt templates and model usage monitoring

Revision ID: 20261007_0004
Revises: 20261007_0003
Create Date: 2026-10-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261007_0004"
down_revision: Union[str, None] = "20261007_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_calls_feature", "model_calls", ["feature"])
    op.create_index("ix_model_calls_created_at", "model_calls", ["created_at"])
    op.create_index("ix_model_calls_created_feature", "model_calls", ["created_at", "feature"])
    op.create_table(
        "monitor_settings",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("daily_token_budget", sa.Integer(), nullable=False, server_default="1000000"),
    )
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.String(), nullable=False),
        sa.Column("versions", sa.JSON(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("prompt_templates")
    op.drop_table("monitor_settings")
    op.drop_index("ix_model_calls_created_feature", table_name="model_calls")
    op.drop_index("ix_model_calls_created_at", table_name="model_calls")
    op.drop_index("ix_model_calls_feature", table_name="model_calls")
    op.drop_table("model_calls")
