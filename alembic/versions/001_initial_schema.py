"""Initial schema — capture existing database state.

Revision ID: 001
Revises:
Create Date: 2026-06-14

Captures the actual schema from backend/database.py including:
- projects, devices, connections, reports, sync_status (existing tables)
- sync_operations (NEW — granular per-entity sync tracking)
- Performance indexes
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema — applies to fresh databases."""

    # ── Projects ────────────────────────────────────────────────────────
    op.create_table(
        'projects',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('description', sa.Text, nullable=False, server_default=''),
        sa.Column('author', sa.Text, nullable=False, server_default=''),
        sa.Column('created_at', sa.Text, nullable=False),
        sa.Column('updated_at', sa.Text, nullable=False),
        sa.Column('status', sa.Text, nullable=False, server_default='draft'),
        if_not_exists=True,
    )

    # ── Devices ─────────────────────────────────────────────────────────
    op.create_table(
        'devices',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('project_id', sa.Text, nullable=False),
        sa.Column('type', sa.Text, nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('category', sa.Text, nullable=False),
        sa.Column('x', sa.REAL, nullable=False),
        sa.Column('y', sa.REAL, nullable=False),
        sa.Column('z', sa.REAL, nullable=False, server_default='0.0'),
        sa.Column('rotation', sa.REAL, nullable=False, server_default='0.0'),
        sa.Column('voltage', sa.REAL, nullable=False, server_default='0.0'),
        sa.Column('current', sa.REAL, nullable=False, server_default='0.0'),
        sa.Column('load', sa.REAL, nullable=False, server_default='0.0'),
        sa.Column('properties', sa.Text, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.Text, nullable=False),
        sa.Column('updated_at', sa.Text, nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        if_not_exists=True,
    )

    # ── Connections ─────────────────────────────────────────────────────
    op.create_table(
        'connections',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('project_id', sa.Text, nullable=False),
        sa.Column('from_id', sa.Text, nullable=False),
        sa.Column('to_id', sa.Text, nullable=False),
        sa.Column('cable_size', sa.Text, nullable=False, server_default='1.5mm²'),
        sa.Column('length', sa.REAL, nullable=False, server_default='0.0'),
        sa.Column('type', sa.Text, nullable=False, server_default='power'),
        sa.Column('created_at', sa.Text, nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        if_not_exists=True,
    )

    # ── Reports ─────────────────────────────────────────────────────────
    op.create_table(
        'reports',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('project_id', sa.Text, nullable=False),
        sa.Column('type', sa.Text, nullable=False),
        sa.Column('name', sa.Text, nullable=False, server_default=''),
        sa.Column('parameters', sa.Text, nullable=False, server_default='{}'),
        sa.Column('status', sa.Text, nullable=False, server_default='pending'),
        sa.Column('created_at', sa.Text, nullable=False),
        sa.Column('completed_at', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        if_not_exists=True,
    )

    # ── Sync Status (existing — project-level sync tracking) ────────────
    op.create_table(
        'sync_status',
        sa.Column('project_id', sa.Text, primary_key=True),
        sa.Column('status', sa.Text, nullable=False, server_default='synced'),
        sa.Column('last_sync', sa.Text, nullable=False),
        sa.Column('pending_changes', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        if_not_exists=True,
    )

    # ── Sync Operations (NEW — granular per-entity sync tracking) ───────
    op.create_table(
        'sync_operations',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('entity_type', sa.Text, nullable=False),
        sa.Column('entity_id', sa.Text, nullable=False),
        sa.Column('target_db', sa.Text, nullable=False),
        sa.Column('status', sa.Text, server_default='pending'),
        sa.Column('last_sync_at', sa.Text, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('retry_count', sa.Integer, server_default='0'),
        if_not_exists=True,
    )

    # ── Indexes for performance ─────────────────────────────────────────
    op.create_index('idx_devices_project', 'devices', ['project_id'], if_not_exists=True)
    op.create_index('idx_connections_project', 'connections', ['project_id'], if_not_exists=True)
    op.create_index('idx_reports_project', 'reports', ['project_id'], if_not_exists=True)
    op.create_index('idx_connections_from', 'connections', ['from_id'], if_not_exists=True)
    op.create_index('idx_connections_to', 'connections', ['to_id'], if_not_exists=True)
    op.create_index('idx_sync_ops_entity', 'sync_operations', ['entity_type', 'entity_id'], if_not_exists=True)


def downgrade() -> None:
    """Remove all tables."""
    op.drop_index('idx_sync_ops_entity', table_name='sync_operations', if_exists=True)
    op.drop_index('idx_connections_to', table_name='connections', if_exists=True)
    op.drop_index('idx_connections_from', table_name='connections', if_exists=True)
    op.drop_index('idx_reports_project', table_name='reports', if_exists=True)
    op.drop_index('idx_connections_project', table_name='connections', if_exists=True)
    op.drop_index('idx_devices_project', table_name='devices', if_exists=True)
    op.drop_table('sync_operations', if_exists=True)
    op.drop_table('sync_status', if_exists=True)
    op.drop_table('reports', if_exists=True)
    op.drop_table('connections', if_exists=True)
    op.drop_table('devices', if_exists=True)
    op.drop_table('projects', if_exists=True)
