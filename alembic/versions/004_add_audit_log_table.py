"""Add audit log table for tracking changes to safety-critical operations.

Revision ID: 004
Revises: 003
Create Date: 2026-06-17

This migration adds an audit_log table to track all changes to 
safety-critical operations in the fire alarm system. This is required
for compliance with NFPA 72 standards for documentation of system changes.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add audit log table for compliance tracking."""
    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('timestamp', sa.Text, nullable=False),
        sa.Column('user_id', sa.String, nullable=False),
        sa.Column('action', sa.Text, nullable=False),  # CREATE, UPDATE, DELETE, VIEW
        sa.Column('entity_type', sa.Text, nullable=False),  # projects, devices, etc.
        sa.Column('entity_id', sa.String, nullable=False),
        sa.Column('old_values', sa.Text),  # JSON string of old values
        sa.Column('new_values', sa.Text),  # JSON string of new values
        sa.Column('ip_address', sa.Text),
        sa.Column('user_agent', sa.Text),
        if_not_exists=True,
    )
    
    # Add indexes for performance
    op.create_index('idx_audit_log_timestamp', 'audit_log', ['timestamp'], if_not_exists=True)
    op.create_index('idx_audit_log_user', 'audit_log', ['user_id'], if_not_exists=True)
    op.create_index('idx_audit_log_entity', 'audit_log', ['entity_type', 'entity_id'], if_not_exists=True)
    op.create_index('idx_audit_log_action', 'audit_log', ['action'], if_not_exists=True)


def downgrade() -> None:
    """Remove audit log table."""
    op.drop_index('idx_audit_log_action', table_name='audit_log', if_exists=True)
    op.drop_index('idx_audit_log_entity', table_name='audit_log', if_exists=True)
    op.drop_index('idx_audit_log_user', table_name='audit_log', if_exists=True)
    op.drop_index('idx_audit_log_timestamp', table_name='audit_log', if_exists=True)
    op.drop_table('audit_log', if_exists=True)