"""backend/db_models.py — SQLAlchemy ORM models for Alembic autogenerate support.

These models mirror the exact schema defined in database.py (_init_schema / _init_schema_pg).
They are used ONLY by Alembic for `alembic revision --autogenerate` to detect schema changes.
The runtime CRUD operations in database.py use raw SQL with parameterized placeholders.

When you modify the schema in database.py, you MUST also update the corresponding
SQLAlchemy model here, then run `alembic revision --autogenerate -m "description"`.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    pass


class Project(Base):
    """A fire alarm engineering project."""

    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, server_default="")
    author = Column(String, nullable=False, server_default="")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    status = Column(
        String,
        nullable=False,
        server_default="draft",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'draft')",
            name="ck_projects_status",
        ),
    )

    # Relationships
    devices = relationship("Device", back_populates="project", cascade="all, delete-orphan")
    connections = relationship("Connection", back_populates="project", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="project", cascade="all, delete-orphan")


class Device(Base):
    """A fire alarm device within a project."""

    __tablename__ = "devices"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    z = Column(Float, nullable=False, server_default="0.0")
    rotation = Column(Float, nullable=False, server_default="0.0")
    voltage = Column(Float, nullable=False, server_default="0.0")
    current = Column(Float, nullable=False, server_default="0.0")
    load = Column(Float, nullable=False, server_default="0.0")
    properties = Column(Text, nullable=False, server_default="{}")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="devices")

    __table_args__ = (
        Index("idx_devices_project", "project_id"),
        Index("idx_devices_type", "type"),
    )


class Connection(Base):
    """A cable connection between two devices."""

    __tablename__ = "connections"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_id = Column(String, nullable=False)
    to_id = Column(String, nullable=False)
    cable_size = Column(String, nullable=False, server_default="1.5mm²")
    length = Column(Float, nullable=False, server_default="0.0")
    type = Column(String, nullable=False, server_default="power")
    created_at = Column(String, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="connections")

    __table_args__ = (
        Index("idx_connections_project", "project_id"),
        Index("idx_connections_from", "from_id"),
        Index("idx_connections_to", "to_id"),
    )


class Report(Base):
    """An engineering report for a project."""

    __tablename__ = "reports"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False, server_default="")
    parameters = Column(Text, nullable=False, server_default="{}")
    status = Column(
        String,
        nullable=False,
        server_default="pending",
    )
    created_at = Column(String, nullable=False)
    completed_at = Column(String, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="reports")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_reports_status",
        ),
        Index("idx_reports_project", "project_id"),
        Index("idx_reports_status", "status"),
    )


class SyncStatus(Base):
    """Status of project synchronization."""

    __tablename__ = "sync_status"

    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status = Column(
        String,
        nullable=False,
        server_default="synced",
    )
    last_sync = Column(String, nullable=False)
    pending_changes = Column(Integer, nullable=False, server_default="0")
    error = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('syncing', 'synced', 'error')",
            name="ck_sync_status_status",
        ),
    )


class SyncOperation(Base):
    """Granular per-entity sync tracking."""

    __tablename__ = "sync_operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    target_db = Column(String, nullable=False)
    status = Column(String, server_default="pending")
    last_sync_at = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    retry_count = Column(Integer, server_default="0")

    __table_args__ = (
        Index("idx_sync_ops_entity", "entity_type", "entity_id"),
        Index("idx_sync_ops_status", "status"),
    )
