"""Add ETAP integration tables (schema drift fix from database.py).

Revision ID: 005
Revises: 004
Create Date: 2026-07-22

This migration brings etap_integrations and etap_sync_logs under Alembic
management. These tables were previously created only via raw SQL in
backend/database.py (_init_schema / _init_schema_pg), causing schema drift
where Alembic migrations did not track their schema.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ETAP integration tables."""
    # -- ETAP Integrations ------------------------------------------
    op.create_table(
        "etap_integrations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("project_id", sa.Text, nullable=False),
        sa.Column("host", sa.Text, nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("password", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_sync", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_etap_integrations_project",
        "etap_integrations",
        ["project_id"],
        if_not_exists=True,
    )

    # -- ETAP Sync Logs ---------------------------------------------
    op.create_table(
        "etap_sync_logs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("project_id", sa.Text, nullable=False),
        sa.Column("direction", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("records_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_etap_sync_logs_project",
        "etap_sync_logs",
        ["project_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_etap_sync_logs_created",
        "etap_sync_logs",
        ["created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove ETAP integration tables."""
    op.drop_index(
        "idx_etap_sync_logs_created",
        table_name="etap_sync_logs",
        if_exists=True,
    )
    op.drop_index(
        "idx_etap_sync_logs_project",
        table_name="etap_sync_logs",
        if_exists=True,
    )
    op.drop_index(
        "idx_etap_integrations_project",
        table_name="etap_integrations",
        if_exists=True,
    )
    op.drop_table("etap_sync_logs", if_exists=True)
    op.drop_table("etap_integrations", if_exists=True)
