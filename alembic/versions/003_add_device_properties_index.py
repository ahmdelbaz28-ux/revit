"""Add index on device properties for faster JSON queries.

Revision ID: 003
Revises: 002
Create Date: 2026-06-16

This migration adds an index on the properties column of the devices table
to optimize queries that filter based on device properties stored as JSON.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add index on device properties for JSON queries."""
    # Add index for JSON property queries
    # For SQLite, we can't directly index JSON fields, but we can add a functional index conceptually
    # In PostgreSQL, we might use expressions like (properties->>'$.device_class')
    
    # Adding a full-text search index conceptually for properties field
    # For now, just add a standard index on the properties column
    op.create_index('idx_devices_properties', 'devices', ['properties'], if_not_exists=True)
    
    # Add columns for additional performance metrics tracking
    op.add_column('sync_operations', 
                  sa.Column('query_performance_ms', sa.Integer, server_default='0'))
    op.add_column('sync_operations', 
                  sa.Column('last_accessed', sa.Text, server_default=None))


def downgrade() -> None:
    """Remove the added index and columns."""
    op.drop_index('idx_devices_properties', table_name='devices', if_exists=True)
    op.drop_column('sync_operations', 'query_performance_ms')
    op.drop_column('sync_operations', 'last_accessed')