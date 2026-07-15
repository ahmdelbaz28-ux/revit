"""Add performance indexes to optimize queries on large datasets.

Revision ID: 002
Revises: 001
Create Date: 2026-06-15

This migration adds critical performance indexes that were identified
as missing during performance testing with large datasets (>10K records).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for large dataset queries."""
    # Existing indexes are already in 001_initial_schema.py
    # Adding additional indexes for performance optimization
    
    # Index on devices table for faster filtering by type and category
    op.create_index('idx_devices_category', 'devices', ['category'], if_not_exists=True)
    op.create_index('idx_devices_created_at', 'devices', ['created_at'], if_not_exists=True)
    
    # Index on connections for faster lookups by from_id and to_id
    op.create_index('idx_connections_from_id', 'connections', ['from_id'], if_not_exists=True)
    op.create_index('idx_connections_to_id', 'connections', ['to_id'], if_not_exists=True)
    op.create_index('idx_connections_type', 'connections', ['type'], if_not_exists=True)
    
    # Index on reports for faster status and date filtering
    op.create_index('idx_reports_created_at', 'reports', ['created_at'], if_not_exists=True)
    op.create_index('idx_reports_type', 'reports', ['type'], if_not_exists=True)
    
    # Composite indexes for common query patterns
    op.create_index('idx_devices_proj_type', 'devices', ['project_id', 'type'], if_not_exists=True)
    op.create_index('idx_devices_proj_cat', 'devices', ['project_id', 'category'], if_not_exists=True)
    

def downgrade() -> None:
    """Remove the added performance indexes."""
    op.drop_index('idx_devices_proj_cat', table_name='devices', if_exists=True)
    op.drop_index('idx_devices_proj_type', table_name='devices', if_exists=True)
    op.drop_index('idx_reports_type', table_name='reports', if_exists=True)
    op.drop_index('idx_reports_created_at', table_name='reports', if_exists=True)
    op.drop_index('idx_connections_type', table_name='connections', if_exists=True)
    op.drop_index('idx_connections_to_id', table_name='connections', if_exists=True)
    op.drop_index('idx_connections_from_id', table_name='connections', if_exists=True)
    op.drop_index('idx_devices_created_at', table_name='devices', if_exists=True)
    op.drop_index('idx_devices_category', table_name='devices', if_exists=True)