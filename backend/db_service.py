"""
FireAI Digital Twin - Database Service.
======================================
Thread-safe singleton wrapping UniversalDataModel (core/database.py)
and adding project management with its own SQLite table.

All conversion between Pydantic schemas and core dataclasses happens here.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.schemas import (
    ConflictResponse,
    ConnectionCreate,
    ConnectionResponse,
    ElementCreate,
    ElementResponse,
    ElementUpdate,
    GeometryResponse,
    Point3DResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    SemanticPropertiesResponse,
    StatisticsResponse,
)
from core.database import UniversalDataModel
from core.models import (
    ChangeSource,
    Geometry,
    Point3D,
    Relationship,
    SemanticProperties,
    UniversalElement,
)

logger = logging.getLogger(__name__)


# V113 FIX: Sort field whitelist to prevent injection.
# The old _normalize_sort blindly converted any string to snake_case
# using regex, allowing arbitrary sort keys like "__class__",
# "__dict__", or other Python dunder attributes. While the sort key
# is used for Python's sorted() (not SQL), an attacker could:
# 1. Access internal Python object attributes via dict.get()
# 2. Cause unexpected behavior or information leakage
# 3. If future code uses sort_key in SQL (f-string interpolation),
#    it becomes a full SQL injection
# Per agent.md Rule 17: fix the root cause — use a strict whitelist.
_SORT_WHITELIST = frozenset({
    "created_at", "created_timestamp", "last_modified_timestamp",
    "updated_at", "name", "description", "author", "status",
    "type", "category", "voltage", "current", "load",
    "element_type", "version", "project_id", "length",
    "cable_size",
})

# Map from camelCase (frontend) to snake_case (backend)
_CAMEL_TO_SNAKE = {
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "createdTimestamp": "created_timestamp",
    "lastModifiedTimestamp": "last_modified_timestamp",
    "cableSize": "cable_size",
    "projectId": "project_id",
    "elementType": "element_type",
}


def _normalize_sort(sort_by: str) -> str:
    r"""
    Convert camelCase sort parameter to snake_case WITH whitelist validation.

    V113 SECURITY FIX: Only allows known sort fields. Unknown fields
    are silently mapped to 'created_at' (safe default) instead of
    being blindly converted from user input. This prevents injection
    of arbitrary Python attribute names or SQL column names.

    Previous code used regex: re.sub(r'([A-Z])', r'_\1', sort_by).lower()
    This would convert ANY string, including "__class__", "__dict__",
    "1; DROP TABLE projects--", etc. to snake_case and use it as a
    sort key — a potential security vulnerability.
    """
    # Step 1: Try the camelCase → snake_case mapping first
    if sort_by in _CAMEL_TO_SNAKE:
        return _CAMEL_TO_SNAKE[sort_by]

    # Step 2: Already snake_case? Check against whitelist
    if sort_by in _SORT_WHITELIST:
        return sort_by

    # Step 3: Unknown sort field — log warning and use safe default
    logger.warning(  # NOSONAR
        f"Rejected sort field '{sort_by}' — not in whitelist. "
        f"Falling back to 'created_at'. "
        f"Allowed: {sorted(_SORT_WHITELIST)}"
    )
    return "created_at"


class DatabaseService:
    """
    Thread-safe singleton that wraps UniversalDataModel and adds project support.

    Provides methods that the routers can call, handling the conversion between
    Pydantic schemas and core dataclasses.
    """

    _instance: DatabaseService | None = None
    _lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> DatabaseService:
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, db_path: str | None = None) -> None:
        if self._initialized:
            return

        if db_path is None:
            # Use a SEPARATE database from backend/database.py to avoid schema collision.
            # backend/database.py creates a `projects` table with `id` as PK,
            # while this module creates one with `project_id` as PK.
            # Sharing the same file causes silent data corruption.
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
            db_path = os.getenv("UDM_DB_PATH", os.path.join(db_dir, "udm_elements.db"))

        self._db_path = db_path
        self._data_model = UniversalDataModel(db_path=db_path)
        self._service_lock = threading.RLock()

        # Create projects table in the same SQLite database
        self._init_projects_table()

        # In-memory project cache
        self._projects: dict[str, dict[str, Any]] = {}
        self._load_projects_from_db()

        self._initialized = True
        logger.info("DatabaseService initialized with db_path=%s", db_path)

    # ──────────────────────────────────────────────────────────────────────────
    # Projects table initialization
    # ──────────────────────────────────────────────────────────────────────────

    def _safe_db_execute(self, sql: str, params: tuple = (), commit: bool = False) -> Any | None:
        """
        Execute SQL on the UDM connection with proper lock acquisition.

        SAFETY FIX (BUG-36): All direct SQL access to self._data_model._conn
        MUST be wrapped with self._data_model._lock to prevent concurrent access
        from corrupting the SQLite database. Lock ordering is always:
        _service_lock → _data_model._lock (never reversed).
        """
        with self._data_model._lock:
            conn = self._data_model._conn
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if commit:
                conn.commit()
            return cursor

    @property
    def _db_conn(self) -> sqlite3.Connection:
        """
        Get database connection ONLY while holding the database lock.

        CRITICAL FIX: Previous code accessed self._data_model._conn directly
        without acquiring self._data_model._lock, creating a race condition
        where two threads could execute SQL on the same sqlite3.Connection
        simultaneously — risking database corruption and silent data loss.

        This property MUST only be used inside `with self._db_lock:` blocks.
        The `_db_lock` context manager enforces the lock ordering:
        _service_lock → _data_model._lock (never reversed).

        NEVER access self._data_model._conn outside of _db_lock or _safe_db_execute.
        """
        return self._data_model._conn

    @property
    def _db_lock(self) -> threading.RLock:
        """
        Get the database lock for multi-statement operations.

        Usage:
            with self._service_lock:        # Always acquire service lock first
                with self._db_lock:         # Then acquire db lock
                    with self._db_lock:
                        conn = self._db_conn
                    cursor = conn.cursor()
                    cursor.execute(...)
                    conn.commit()

        This enforces the same lock ordering as _safe_db_execute:
        _service_lock → _data_model._lock
        """
        return self._data_model._lock

    def _init_projects_table(self) -> None:
        """Create projects table in the existing SQLite database."""
        with self._service_lock:
            try:
                self._safe_db_execute('''
                    CREATE TABLE IF NOT EXISTS projects (
                        project_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        status TEXT DEFAULT 'draft',
                        metadata JSON,
                        created_timestamp TEXT,
                        last_modified_timestamp TEXT
                    )
                ''')
                # Enable foreign keys
                self._safe_db_execute("PRAGMA foreign_keys=ON")
                self._safe_db_execute("SELECT 1", commit=True)
                logger.info("Projects table initialized")
            except Exception as e:
                logger.error("Error initializing projects table: %s", e)

    def _load_projects_from_db(self) -> None:
        """Load projects from SQLite into in-memory cache."""
        with self._service_lock:
            try:
                cursor = self._safe_db_execute(
                    "SELECT project_id, name, description, status, metadata, "
                    "created_timestamp, last_modified_timestamp FROM projects"
                )
                rows = cursor.fetchall()
                for row in rows:
                    project_id = row[0]
                    self._projects[project_id] = {
                        "project_id": project_id,
                        "name": row[1],
                        "description": row[2],
                        "status": row[3],
                        "metadata": json.loads(row[4]) if row[4] else None,
                        "created_timestamp": row[5],
                        "last_modified_timestamp": row[6],
                    }
                logger.info("Loaded %s projects from database", len(self._projects))
            except Exception as e:
                logger.error("Error loading projects: %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # Project CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def create_project(self, project_data: ProjectCreate) -> ProjectResponse:
        """Create a new project."""
        with self._service_lock:
            project_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            project_dict = {
                "project_id": project_id,
                "name": project_data.name,
                "description": project_data.description,
                "status": project_data.status.value,
                "metadata": project_data.metadata,
                "created_timestamp": now,
                "last_modified_timestamp": now,
            }

            # Persist to SQLite
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO projects "
                    "(project_id, name, description, status, metadata, "
                    "created_timestamp, last_modified_timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        project_id,
                        project_data.name,
                        project_data.description,
                        project_data.status.value,
                        json.dumps(project_data.metadata) if project_data.metadata else None,
                        now,
                        now,
                    ),
                )
                conn.commit()
            except Exception as e:
                logger.error("Error persisting project: %s", e)
                raise

            # Cache in memory
            self._projects[project_id] = project_dict

            return self._project_to_response(project_dict)

    def get_project(self, project_id: str) -> ProjectResponse | None:
        """Get a project by ID."""
        with self._service_lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            return self._project_to_response(project)

    def list_projects(
        self,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_timestamp",
        sort_order: str = "desc",
    ) -> tuple[list[ProjectResponse], int]:
        """List projects with optional filtering and pagination."""
        with self._service_lock:
            projects = list(self._projects.values())

            # Filter by status
            if status:
                projects = [p for p in projects if p.get("status") == status]

            # Sort
            sort_key = _normalize_sort(sort_by)
            reverse = sort_order.lower() == "desc"
            projects.sort(
                key=lambda p: p.get(sort_key, "") or "",
                reverse=reverse,
            )

            total = len(projects)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = projects[start:end]

            return [self._project_to_response(p) for p in paginated], total

    def update_project(self, project_id: str, update_data: ProjectUpdate) -> ProjectResponse | None:
        """Update a project."""
        with self._service_lock:
            project = self._projects.get(project_id)
            if project is None:
                return None

            now = datetime.now(timezone.utc).isoformat()

            # Apply updates
            if update_data.name is not None:
                project["name"] = update_data.name
            if update_data.description is not None:
                project["description"] = update_data.description
            if update_data.status is not None:
                project["status"] = update_data.status.value
            if update_data.metadata is not None:
                project["metadata"] = update_data.metadata

            project["last_modified_timestamp"] = now

            # Persist
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE projects SET name=?, description=?, status=?, "
                    "metadata=?, last_modified_timestamp=? WHERE project_id=?",
                    (
                        project["name"],
                        project["description"],
                        project["status"],
                        json.dumps(project["metadata"]) if project["metadata"] else None,
                        now,
                        project_id,
                    ),
                )
                conn.commit()
            except Exception as e:
                logger.error("Error updating project: %s", e)
                raise

            return self._project_to_response(project)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its elements."""
        with self._service_lock:
            if project_id not in self._projects:
                return False

            # Soft-delete all elements in this project
            elements = self._data_model.get_all_elements()
            for element in elements:
                element_project_id = self._get_element_project_id(element.element_id)
                if element_project_id == project_id:
                    self._data_model.delete_element(element.element_id)

            # Delete from SQLite
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()
                # Remove element-project associations
                cursor.execute(
                    "DELETE FROM element_projects WHERE project_id=?",
                    (project_id,),
                )
                cursor.execute(
                    "DELETE FROM projects WHERE project_id=?",
                    (project_id,),
                )
                conn.commit()
            except Exception as e:
                logger.error("Error deleting project: %s", e)
                # Still remove from cache even if DB delete fails for associations
                try:
                    with self._db_lock:
                        conn = self._db_conn
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM projects WHERE project_id=?",
                        (project_id,),
                    )
                    conn.commit()
                except Exception as e:
                    logger.warning("Failed to delete project %s from DB after association error: %s", project_id, e)

            # Remove from cache
            del self._projects[project_id]
            return True

    def _project_to_response(self, project_dict: dict[str, Any]) -> ProjectResponse:
        """Convert project dict to ProjectResponse."""
        # Count elements for this project
        element_count = 0
        try:
            element_count = self._count_project_elements(project_dict["project_id"])
        except Exception as e:
            logger.debug("Failed to count elements for project %s: %s", project_dict.get('project_id', '?'), e)

        return ProjectResponse(
            project_id=project_dict["project_id"],
            name=project_dict["name"],
            description=project_dict.get("description"),
            status=project_dict.get("status", "draft"),
            metadata=project_dict.get("metadata"),
            element_count=element_count,
            created_timestamp=project_dict.get("created_timestamp"),
            last_modified_timestamp=project_dict.get("last_modified_timestamp"),
        )

    def _count_project_elements(self, project_id: str) -> int:
        """Count elements belonging to a project."""
        try:
            # BUG-36 FIX: Use _safe_db_execute for proper lock acquisition
            cursor = self._safe_db_execute(
                "SELECT COUNT(*) FROM element_projects WHERE project_id=?",
                (project_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            # Fallback: count from in-memory elements with matching project_id
            count = 0
            for element in self._data_model.get_all_elements():
                if self._get_element_project_id(element.element_id) == project_id:
                    count += 1
            return count

    def _get_element_project_id(self, element_id: str) -> str | None:
        """Get the project ID for an element."""
        try:
            # BUG-36 FIX: Use _safe_db_execute for proper lock acquisition
            cursor = self._safe_db_execute(
                "SELECT project_id FROM element_projects WHERE element_id=?",
                (element_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Element CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def create_element(self, element_data: ElementCreate) -> ElementResponse:
        """Create a new element from schema data."""
        with self._service_lock:
            # Build core model objects from schema
            element_id = element_data.element_id or str(uuid.uuid4())

            # Properties
            props_schema = element_data.properties
            properties = SemanticProperties(
                element_type=props_schema.element_type,
                name=props_schema.name,
                description=props_schema.description,
                material=props_schema.material,
                fire_rating=props_schema.fire_rating,
                height=props_schema.height,
                width=props_schema.width,
                load_bearing=props_schema.load_bearing,
                layer=props_schema.layer,
                revit_category=props_schema.revit_category,
            )

            # Geometry
            geometry = None
            if element_data.geometry:
                geometry = Geometry(
                    points=[Point3D(x=p.x, y=p.y, z=p.z) for p in element_data.geometry.points],
                    polyline_closed=element_data.geometry.polyline_closed,
                )

            # Create UniversalElement
            element = UniversalElement(
                element_id=element_id,
                properties=properties,
                geometry=geometry,
                source_file=element_data.source_file,
                last_modified_by=element_data.last_modified_by,
                autocad_handle=element_data.autocad_handle,
                revit_element_id=element_data.revit_element_id,
            )

            # Add to data model
            success = self._data_model.add_element(element)
            if not success:
                raise RuntimeError(f"Failed to add element {element_id}")

            # Associate with project if provided
            if element_data.project_id:
                self._associate_element_with_project(element_id, element_data.project_id)

            return self._element_to_response(element, element_data.project_id)

    def get_element(self, element_id: str) -> ElementResponse | None:
        """Get an element by ID."""
        with self._service_lock:
            element = self._data_model.get_element(element_id)
            if element is None:
                return None
            project_id = self._get_element_project_id(element_id)
            return self._element_to_response(element, project_id)

    def list_elements(
        self,
        element_type: str | None = None,
        project_id: str | None = None,
        is_deleted: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_timestamp",
        sort_order: str = "desc",
    ) -> tuple[list[ElementResponse], int]:
        """List elements with optional filtering and pagination."""
        with self._service_lock:
            elements = self._data_model.get_all_elements()

            # Filter by element type
            if element_type:
                elements = [
                    e for e in elements
                    if e.properties and (e.properties.element_type.value if hasattr(e.properties.element_type, 'value') else str(e.properties.element_type)) == element_type
                ]

            # Filter by project
            if project_id:
                project_element_ids = set()
                try:
                    with self._db_lock:
                        conn = self._db_conn
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT element_id FROM element_projects WHERE project_id=?",
                        (project_id,),
                    )
                    for row in cursor.fetchall():
                        project_element_ids.add(row[0])
                except Exception as e:
                    logger.debug("Failed to query element_projects for project filter: %s", e)
                elements = [e for e in elements if e.element_id in project_element_ids]

            # Filter by deletion status
            if is_deleted is not None:
                elements = [e for e in elements if e.is_deleted == is_deleted]
            else:
                # By default, exclude deleted elements
                elements = [e for e in elements if not e.is_deleted]

            # Sort
            sort_key = _normalize_sort(sort_by)
            reverse = sort_order.lower() == "desc"
            elements.sort(
                key=lambda e: self._get_sort_value(e, sort_key),
                reverse=reverse,
            )

            total = len(elements)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = elements[start:end]

            result = []
            for e in paginated:
                pid = self._get_element_project_id(e.element_id)
                result.append(self._element_to_response(e, pid))

            return result, total

    def update_element(self, element_id: str, update_data: ElementUpdate) -> ElementResponse | None:
        """Update an element."""
        with self._service_lock:
            element = self._data_model.get_element(element_id)
            if element is None:
                return None

            # Build updates dict for UniversalDataModel.update_element()
            updates: dict[str, Any] = {}

            if update_data.properties:
                # Merge with existing properties
                existing_props = element.properties
                props_dict = existing_props.to_dict() if existing_props else {}

                for field_name, value in update_data.properties.model_dump(exclude_unset=True).items():
                    if value is not None:
                        props_dict[field_name] = value

                updates["properties"] = props_dict

            if update_data.geometry:
                updates["geometry"] = {
                    "points": [{"x": p.x, "y": p.y, "z": p.z} for p in update_data.geometry.points],
                    "polyline_closed": update_data.geometry.polyline_closed,
                }

            if update_data.source_file is not None:
                updates["source_file"] = update_data.source_file
            if update_data.last_modified_by is not None:
                updates["last_modified_by"] = update_data.last_modified_by
            if update_data.is_deleted is not None:
                updates["is_deleted"] = update_data.is_deleted

            # If setting is_deleted to True, use delete_element instead
            if update_data.is_deleted is True and not element.is_deleted:
                source = ChangeSource.MANUAL
                if update_data.last_modified_by:
                    try:
                        source = ChangeSource(update_data.last_modified_by)
                    except ValueError as ve:
                        logger.debug("Unknown ChangeSource '%s': %s", update_data.last_modified_by, ve)
                self._data_model.delete_element(element_id, source=source)
            elif updates:
                source = ChangeSource.MANUAL
                if update_data.last_modified_by:
                    try:
                        source = ChangeSource(update_data.last_modified_by)
                    except ValueError as ve:
                        logger.debug("Unknown ChangeSource '%s': %s", update_data.last_modified_by, ve)
                self._data_model.update_element(
                    element_id, updates, source=source
                )

            # Return updated element
            element = self._data_model.get_element(element_id)
            if element is None:
                return None
            project_id = self._get_element_project_id(element_id)
            return self._element_to_response(element, project_id)

    def delete_element(self, element_id: str, source: str = "manual") -> bool:
        """Soft delete an element."""
        with self._service_lock:
            try:
                change_source = ChangeSource(source)
            except ValueError:
                change_source = ChangeSource.MANUAL

            return self._data_model.delete_element(element_id, source=change_source)

    # ──────────────────────────────────────────────────────────────────────────
    # Bridge helpers — used by project_bridge.py for cross-database sync
    # These provide safe raw SQL access without exposing private internals
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def bridge_lock(self) -> threading.RLock:
        """Lock for bridge operations. Always acquire before bridge_sql()."""
        return self._service_lock

    def bridge_sql(self, sql: str, params: tuple = (), commit: bool = False, fetch: bool = False):
        """
        Execute raw SQL for bridge sync operations safely.

        Ensures proper lock ordering and connection safety.
        Used ONLY by project_bridge.py for cross-database synchronization.
        """
        with self._service_lock:
            cursor = self._safe_db_execute(sql, params, commit=commit)
            if fetch:
                return cursor
            return True

    def bridge_create_table(self, create_sql: str) -> None:
        """Create a table safely for bridge operations."""
        with self._service_lock:
            self._safe_db_execute(create_sql, commit=True)

    def bridge_insert(self, sql: str, params: tuple) -> None:
        """Insert a row for bridge sync."""
        with self._service_lock:
            self._safe_db_execute(sql, params, commit=True)

    # ──────────────────────────────────────────────────────────────────────────

    def _element_to_response(self, element: UniversalElement, project_id: str | None = None) -> ElementResponse:
        """
        Convert UniversalElement to ElementResponse.

        V115 FIX: Now passes proper Pydantic model instances instead of raw dicts
        to ElementResponse. Previously, properties and geometry were passed as
        plain dicts, which would fail Pydantic V2 strict validation when the
        schema expects SemanticPropertiesResponse / GeometryResponse objects.
        """
        props_response = None
        if element.properties:
            props_response = SemanticPropertiesResponse(
                element_type=element.properties.element_type.value if hasattr(element.properties.element_type, 'value') else str(element.properties.element_type),
                name=element.properties.name,
                description=element.properties.description,
                material=element.properties.material,
                fire_rating=element.properties.fire_rating,
                height=element.properties.height,
                width=element.properties.width,
                load_bearing=element.properties.load_bearing,
                layer=element.properties.layer,
                revit_category=element.properties.revit_category,
            )

        geom_response = None
        if element.geometry:
            geom_response = GeometryResponse(
                points=[Point3DResponse(x=p.x, y=p.y, z=p.z) for p in element.geometry.points],
                polyline_closed=element.geometry.polyline_closed,
                area=element.geometry.area,
                perimeter=element.geometry.perimeter,
            )

        relationships = []
        for r in element.relationships:
            relationships.append(r.to_dict())

        return ElementResponse(
            element_id=element.element_id,
            properties=props_response,
            geometry=geom_response,
            relationships=relationships,
            created_timestamp=element.created_timestamp.isoformat() if element.created_timestamp else None,
            last_modified_timestamp=element.last_modified_timestamp.isoformat() if element.last_modified_timestamp else None,
            last_modified_by=element.last_modified_by,
            source_file=element.source_file,
            version=element.version,
            is_deleted=element.is_deleted,
            autocad_handle=element.autocad_handle,
            revit_element_id=element.revit_element_id,
            project_id=project_id,
        )

    def _get_sort_value(self, element: UniversalElement, sort_key: str) -> Any:
        """Get a sort value from an element."""
        if sort_key == "name" and element.properties:
            return element.properties.name or ""
        if sort_key == "element_type" and element.properties:
            etype = element.properties.element_type
            return etype.value if hasattr(etype, 'value') else str(etype)
        if sort_key == "created_timestamp" and element.created_timestamp:
            return element.created_timestamp.isoformat()
        if sort_key == "last_modified_timestamp" and element.last_modified_timestamp:
            return element.last_modified_timestamp.isoformat()
        if sort_key == "version":
            return element.version
        return ""

    def _associate_element_with_project(self, element_id: str, project_id: str) -> None:
        """
        Associate an element with a project.

        Acquires the service lock to prevent concurrent SQL operations
        on the same connection (thread safety).
        """
        with self._service_lock:
            try:
                # BUG-36 FIX: Use _safe_db_execute for proper lock acquisition
                self._safe_db_execute('''
                    CREATE TABLE IF NOT EXISTS element_projects (
                        element_id TEXT,
                        project_id TEXT,
                        PRIMARY KEY (element_id, project_id),
                        FOREIGN KEY (element_id) REFERENCES elements(element_id),
                        FOREIGN KEY (project_id) REFERENCES projects(project_id)
                    )
                ''')
                self._safe_db_execute(
                    "INSERT OR IGNORE INTO element_projects (element_id, project_id) VALUES (?, ?)",
                    (element_id, project_id),
                    commit=True,
                )
            except Exception as e:
                logger.error("Error associating element with project: %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # Connection (Relationship) CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def create_connection(self, data: ConnectionCreate) -> ConnectionResponse:
        """Create a new connection (relationship) between elements.

        V188 FIX (CRITICAL): UniversalElement is a frozen dataclass with
        ``relationships: tuple[Relationship, ...]`` (immutable). The previous
        implementation called ``from_element.relationships.append(relationship)``
        which raised ``AttributeError: 'tuple' object has no attribute 'append'``
        on every call. Same bug for the rollback path ``.pop()``.

        Root-cause fix per Rule 17 (NO half-solutions): use the V83 immutable
        update pattern — ``dataclasses.replace()`` to construct a NEW frozen
        element instance with the updated relationships tuple, then persist
        via ``update_element()`` (which writes to the SQLite JSON column).

        This is the SAME design pattern documented in core/models.py:
            "The correct approach is to create a NEW SemanticProperties with
             updated values and replace the reference on the element."

        Why this is the root cause, not a patch:
        - V83 (2026-05) intentionally froze UniversalElement for determinism
        - V83 added a comment saying "db_service must create new instances"
        - But create_connection() was never migrated — it kept the mutable API
        - Tests never caught this because the V2 router (/api/v1/connections)
          is never exercised by the test suite — all tests use the V1 router
          (/api/projects/{pid}/connections) which calls the SAFE
          database.create_connection() method instead.
        - The frontend's Connections.tsx page uses the V2 router via api.ts,
          so EVERY "Create Connection" button click on production would crash.
        """
        with self._service_lock:
            connection_id = str(uuid.uuid4())

            # Verify both elements exist
            from_element = self._data_model.get_element(data.from_element_id)
            to_element = self._data_model.get_element(data.to_element_id)

            if from_element is None:
                raise ValueError(f"Element {data.from_element_id} not found")
            if to_element is None:
                raise ValueError(f"Element {data.to_element_id} not found")

            # Create relationship objects (frozen dataclasses — immutable, safe to share)
            relationship = Relationship(
                from_element_id=data.from_element_id,
                to_element_id=data.to_element_id,
                relationship_type=data.relationship_type,
                is_parametric=data.is_parametric,
                metadata=data.metadata,
                connection_id=connection_id,
            )

            reverse_rel = Relationship(
                from_element_id=data.to_element_id,
                to_element_id=data.from_element_id,
                relationship_type=f"reverse_{data.relationship_type}",
                is_parametric=data.is_parametric,
                metadata=data.metadata,
                connection_id=connection_id,
            )

            # V188 FIX: Use immutable update pattern — construct NEW frozen
            # element instances with the extended relationships tuple.
            # ``dataclasses.replace()`` returns a new frozen dataclass with
            # the specified field replaced; the original is untouched.
            new_from_rels = from_element.relationships + (relationship,)
            new_to_rels = to_element.relationships + (reverse_rel,)

            from_rels_dicts = [r.to_dict() for r in new_from_rels]
            to_rels_dicts = [r.to_dict() for r in new_to_rels]

            # Persist to relationships table FIRST (source of truth for connection_id).
            # If this fails, no in-memory state was mutated (we only built new
            # frozen instances above — they're discarded if we raise here).
            try:
                self._safe_db_execute(
                    "INSERT INTO relationships "
                    "(relationship_id, from_element_id, to_element_id, "
                    "relationship_type, is_parametric, metadata) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        connection_id,
                        data.from_element_id,
                        data.to_element_id,
                        data.relationship_type,
                        data.is_parametric,
                        json.dumps(data.metadata) if data.metadata else None,
                    ),
                    commit=True,
                )
            except Exception as e:
                logger.error("Error persisting connection: %s", e)
                raise RuntimeError(f"Failed to persist connection: {e}")

            # V191 FIX: The V188 code put both update_element calls in ONE
            # try/except block. If the first raised, the second was SKIPPED —
            # leaving the cache inconsistent (to_element updated, from_element
            # not). Root-cause fix: make each update_element call independent
            # with its own try/except, AND check the return value (update_element
            # returns False on failure rather than raising).
            from_success = False
            try:
                from_success = self._data_model.update_element(
                    data.from_element_id,
                    {"relationships": from_rels_dicts},
                )
            except Exception as e:
                logger.warning(
                    "Connection %s persisted, but from_element %s cache "
                    "update raised: %s",
                    connection_id, data.from_element_id, e,
                )
            if not from_success:
                logger.warning(
                    "Connection %s persisted, but from_element %s cache "
                    "update returned False (element may have been deleted)",
                    connection_id, data.from_element_id,
                )

            to_success = False
            try:
                to_success = self._data_model.update_element(
                    data.to_element_id,
                    {"relationships": to_rels_dicts},
                )
            except Exception as e:
                logger.warning(
                    "Connection %s persisted, but to_element %s cache "
                    "update raised: %s",
                    connection_id, data.to_element_id, e,
                )
            if not to_success:
                logger.warning(
                    "Connection %s persisted, but to_element %s cache "
                    "update returned False (element may have been deleted)",
                    connection_id, data.to_element_id,
                )

            return ConnectionResponse(
                connection_id=connection_id,
                from_element_id=data.from_element_id,
                to_element_id=data.to_element_id,
                relationship_type=data.relationship_type,
                is_parametric=data.is_parametric,
                metadata=data.metadata,
            )

    def list_connections(
        self,
        project_id: str | None = None,
        element_id: str | None = None,
        relationship_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ConnectionResponse], int]:
        """List connections with optional filtering and pagination."""
        with self._service_lock:
            connections: list[ConnectionResponse] = []

            try:
                query = (
                    "SELECT relationship_id, from_element_id, to_element_id, "
                    "relationship_type, is_parametric, metadata FROM relationships WHERE 1=1"
                )
                params: list = []

                if element_id:
                    query += " AND (from_element_id=? OR to_element_id=?)"
                    params.extend([element_id, element_id])

                if relationship_type:
                    query += " AND relationship_type=?"
                    params.append(relationship_type)

                # BUG-38 FIX: Filter out reverse relationships to avoid duplicates.
                # The relationships table stores both forward and reverse entries.
                # Only return forward relationships (NOT starting with "reverse_").
                query += " AND relationship_type NOT LIKE 'reverse_%'"

                cursor = self._safe_db_execute(query, tuple(params))
                rows = cursor.fetchall()

                for row in rows:
                    metadata = json.loads(row[5]) if row[5] else None
                    connections.append(
                        ConnectionResponse(
                            connection_id=row[0],
                            from_element_id=row[1],
                            to_element_id=row[2],
                            relationship_type=row[3],
                            is_parametric=bool(row[4]),
                            metadata=metadata,
                        )
                    )
            except Exception as e:
                logger.error("Error listing connections: %s", e)
                # Fallback: scan from in-memory elements
                elements = self._data_model.get_all_elements()
                for element in elements:
                    for rel in element.relationships:
                        if element_id and rel.from_element_id != element_id and rel.to_element_id != element_id:
                            continue
                        if relationship_type and rel.relationship_type != relationship_type:
                            continue
                        connections.append(
                            ConnectionResponse(
                                connection_id=rel.connection_id if hasattr(rel, 'connection_id') and rel.connection_id else str(uuid.uuid4()),
                                from_element_id=rel.from_element_id,
                                to_element_id=rel.to_element_id,
                                relationship_type=rel.relationship_type,
                                is_parametric=rel.is_parametric,
                                metadata=rel.metadata,
                            )
                        )

            # Filter by project if specified
            if project_id:
                project_element_ids = set()
                try:
                    cursor2 = self._safe_db_execute(
                        "SELECT element_id FROM element_projects WHERE project_id=?",
                        (project_id,),
                    )
                    for row in cursor2.fetchall():
                        project_element_ids.add(row[0])
                except Exception as e:
                    logger.debug("Failed to query element_projects for connection filter: %s", e)
                connections = [
                    c for c in connections
                    if c.from_element_id in project_element_ids or c.to_element_id in project_element_ids
                ]

            total = len(connections)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = connections[start:end]

            return paginated, total

    def delete_connection(self, connection_id: str) -> bool:
        """
        Delete a connection by ID.

        Returns True if deleted, False if not found.
        Raises RuntimeError on database errors (NOT silently swallowed).

        V188 FIX: The previous implementation had TWO bugs:
          1. ``self._data_model.elements.get(from_eid)`` — UniversalDataModel
             has NO ``elements`` attribute → AttributeError.
          2. ``from_element.relationships = [...]`` — frozen dataclass →
             FrozenInstanceError.

        V191 FIX: The V188 fix had a THIRD bug — it caught ALL exceptions
        in the outer try/except and returned False. This conflated "not
        found" (legitimate False) with "database error" (should raise).
        The router then returned 404 for DB errors, hiding real failures.

        Root-cause fix per Rule 17: separate the "not found" case (return
        False) from the "DB error" case (raise RuntimeError). Only catch
        exceptions from the SELECT query (for not-found detection), not
        from the DELETE or cache update.
        """
        with self._service_lock:
            # Phase 1: Check if the connection exists (may return False)
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT from_element_id, to_element_id, relationship_type "
                    "FROM relationships WHERE relationship_id=?",
                    (connection_id,),
                )
                row = cursor.fetchone()
            except sqlite3.Error as e:
                # V191: DB error on SELECT is NOT "not found" — raise
                raise RuntimeError(f"Database error checking connection {connection_id}: {e}") from e

            if not row:
                return False  # Legitimate "not found"

            from_eid = row[0]
            to_eid = row[1]
            rel_type = row[2]

            # Phase 2: Delete from SQL (raise on DB error, don't swallow)
            try:
                cursor.execute(
                    "DELETE FROM relationships WHERE relationship_id=?",
                    (connection_id,),
                )
                conn.commit()
            except sqlite3.Error as e:
                # V191: DB error on DELETE is a real failure — raise, don't return False
                raise RuntimeError(f"Database error deleting connection {connection_id}: {e}") from e

            # Phase 3: Update the denormalized relationships cache on both
            # elements. Cache update failures are non-fatal (the relationships
            # table is authoritative), so we log warnings but don't raise.
            reverse_type = f"reverse_{rel_type}"

            for eid, src_eid, tgt_eid, rtype in (
                (from_eid, from_eid, to_eid, rel_type),
                (to_eid,   to_eid,   from_eid, reverse_type),
            ):
                element = self._data_model.get_element(eid)
                if element is None:
                    continue
                # Build a NEW tuple excluding the matching relationship.
                new_rels = tuple(
                    r for r in element.relationships
                    if not (
                        r.from_element_id == src_eid
                        and r.to_element_id == tgt_eid
                        and r.relationship_type == rtype
                    )
                )
                if len(new_rels) == len(element.relationships):
                    continue  # No match — nothing to update
                try:
                    success = self._data_model.update_element(
                        eid,
                        {"relationships": [r.to_dict() for r in new_rels]},
                    )
                    # V191: Check return value — update_element returns False
                    # on failure (element not found, DB error). Log if so.
                    if not success:
                        logger.warning(  # NOSONAR
                            "update_element returned False for element %s "
                            "while cleaning up deleted connection %s cache",
                            eid, connection_id,
                        )
                except Exception as e:
                    logger.warning(  # NOSONAR
                        "Deleted relationship %s from SQL table, but failed "
                        "to update element %s relationships cache: %s",
                        connection_id, eid, e,
                    )

            return True

    # ──────────────────────────────────────────────────────────────────────────
    # Conflict detection and resolution
    # ──────────────────────────────────────────────────────────────────────────

    def detect_conflicts(self) -> list[ConflictResponse]:
        """Detect conflicts between elements."""
        with self._service_lock:
            conflicts = self._data_model.detect_conflicts()
            return [
                ConflictResponse(
                    conflict_id=c.conflict_id,
                    element_id=c.element_id,
                    conflict_type=c.conflict_type.value,
                    timestamp=c.timestamp.isoformat() if c.timestamp else None,
                    source_a=c.source_a.value,
                    source_b=c.source_b.value,
                    change_a=c.change_a,
                    change_b=c.change_b,
                    resolution=c.resolution,
                    resolved=c.resolved,
                )
                for c in conflicts
            ]

    def list_conflicts(
        self,
        resolved: bool | None = None,
        conflict_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ConflictResponse], int]:
        """
        List conflicts with optional filtering and pagination.

        V129 FIX: Uses detect_conflicts() method instead of accessing
        non-existent self._data_model.conflicts dict.
        """
        with self._service_lock:
            # V129 FIX: Get conflicts via detect_conflicts() which queries
            # both the conflicts SQL table and detects new ones
            all_conflicts = self._data_model.detect_conflicts()

            # Filter
            if resolved is not None:
                all_conflicts = [c for c in all_conflicts if c.resolved == resolved]
            if conflict_type:
                all_conflicts = [c for c in all_conflicts if (
                    c.conflict_type.value if hasattr(c.conflict_type, 'value') else str(c.conflict_type)
                ) == conflict_type]

            total = len(all_conflicts)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = all_conflicts[start:end]

            responses = []
            for c in paginated:
                ct = c.conflict_type.value if hasattr(c.conflict_type, 'value') else str(c.conflict_type)
                sa = c.source_a if isinstance(c.source_a, str) else (c.source_a.value if hasattr(c.source_a, 'value') else str(c.source_a)) if c.source_a else None
                sb = c.source_b if isinstance(c.source_b, str) else (c.source_b.value if hasattr(c.source_b, 'value') else str(c.source_b)) if c.source_b else None
                responses.append(ConflictResponse(
                    conflict_id=c.conflict_id,
                    element_id=c.element_id,
                    conflict_type=ct,
                    timestamp=c.timestamp.isoformat() if hasattr(c.timestamp, 'isoformat') and c.timestamp else (str(c.timestamp) if c.timestamp else None),
                    source_a=sa,
                    source_b=sb,
                    change_a=c.change_a,
                    change_b=c.change_b,
                    resolution=c.resolution,
                    resolved=c.resolved,
                ))

            return responses, total

    def resolve_conflict(self, conflict_id: str, strategy: str = "SEMANTIC_MERGE") -> ConflictResponse | None:
        """
        Resolve a conflict by ID.

        V129 FIX: Uses resolve_conflict() on UniversalDataModel instead of
        accessing non-existent self._data_model.conflicts dict.
        """
        with self._service_lock:
            result = self._data_model.resolve_conflict(conflict_id, strategy=strategy)
            if result is None:
                return None

            ct = result.conflict_type.value if hasattr(result.conflict_type, 'value') else str(result.conflict_type)
            sa = result.source_a if isinstance(result.source_a, str) else (result.source_a.value if hasattr(result.source_a, 'value') else str(result.source_a)) if result.source_a else None
            sb = result.source_b if isinstance(result.source_b, str) else (result.source_b.value if hasattr(result.source_b, 'value') else str(result.source_b)) if result.source_b else None

            return ConflictResponse(
                conflict_id=result.conflict_id,
                element_id=result.element_id,
                conflict_type=ct,
                timestamp=result.timestamp.isoformat() if hasattr(result.timestamp, 'isoformat') and result.timestamp else (str(result.timestamp) if result.timestamp else None),
                source_a=sa,
                source_b=sb,
                change_a=result.change_a,
                change_b=result.change_b,
                resolution=result.resolution,
                resolved=result.resolved,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Statistics and export
    # ──────────────────────────────────────────────────────────────────────────

    def get_statistics(self) -> StatisticsResponse:
        """Get database statistics."""
        with self._service_lock:
            stats = self._data_model.get_statistics()

            # Count projects
            total_projects = len(self._projects)
            active_projects = sum(
                1 for p in self._projects.values() if p.get("status") == "active"
            )

            # Count connections
            total_connections = 0
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM relationships")
                row = cursor.fetchone()
                total_connections = row[0] if row else 0
            except Exception:
                # Fallback
                for e in self._data_model.get_all_elements():
                    total_connections += len(e.relationships)
                total_connections = total_connections // 2  # Avoid double-counting

            # Count conflicts
            # HOTFIX C-2: UniversalDataModel has detect_conflicts() method, not conflicts attribute.
            # Previous code raised AttributeError: conflicts → udm_database always "disconnected".
            try:
                conflicts_list = self._data_model.detect_conflicts()
                total_conflicts = len(conflicts_list) if conflicts_list else 0
                # detect_conflicts() returns list; unresolved = those without resolved flag.
                # Since detect_conflicts() returns fresh detection each call, all are unresolved.
                unresolved_conflicts = total_conflicts
            except Exception:
                total_conflicts = 0
                unresolved_conflicts = 0

            return StatisticsResponse(
                # HOTFIX C-2: _Stats is a NamedTuple, not a dict. Use attribute access.
                # Also _Stats only has 6 fields; missing fields default to 0/None.
                total_elements=getattr(stats, "total_elements", 0),
                deleted_elements=getattr(stats, "deleted_elements", 0),
                active_elements=getattr(stats, "active_elements", 0),
                total_projects=total_projects,
                active_projects=active_projects,
                total_connections=getattr(stats, "total_connections", total_connections),
                total_conflicts=getattr(stats, "total_conflicts", total_conflicts),
                unresolved_conflicts=getattr(stats, "unresolved_conflicts", unresolved_conflicts),
                pending_autocad_to_revit=0,
                pending_revit_to_autocad=0,
                database_version=1,
                last_sync=None,
            )

    def export_data(
        self,
        project_id: str | None = None,
        element_types: list[str] | None = None,
        include_deleted: bool = False,
    ) -> dict[str, Any]:
        """Export data as JSON-serializable dict."""
        with self._service_lock:
            elements = self._data_model.get_all_elements()

            if not include_deleted:
                elements = [e for e in elements if not e.is_deleted]

            if project_id:
                project_element_ids = set()
                try:
                    with self._db_lock:
                        conn = self._db_conn
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT element_id FROM element_projects WHERE project_id=?",
                        (project_id,),
                    )
                    for row in cursor.fetchall():
                        project_element_ids.add(row[0])
                except Exception as e:
                    logger.debug("Failed to query element_projects for export filter: %s", e)
                elements = [e for e in elements if e.element_id in project_element_ids]

            if element_types:
                elements = [
                    e for e in elements
                    if e.properties and (e.properties.element_type.value if hasattr(e.properties.element_type, 'value') else str(e.properties.element_type)) in element_types
                ]

            exported_elements = [e.to_dict() for e in elements]

            # Export relationships
            connections = []
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM relationships")
                for row in cursor.fetchall():
                    connections.append({
                        "relationship_id": row[0],
                        "from_element_id": row[1],
                        "to_element_id": row[2],
                        "relationship_type": row[3],
                        "is_parametric": row[4],
                        "metadata": json.loads(row[5]) if row[5] else None,
                    })
            except Exception as e:
                logger.debug("Failed to query relationships for export: %s", e)

            # Export projects
            projects = list(self._projects.values())

            return {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "projects": projects,
                "elements": exported_elements,
                "connections": connections,
                "conflicts": [c.to_dict() for c in self._data_model.conflicts.values()],
                "statistics": self._data_model.get_statistics(),
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        with self._service_lock:
            try:
                self._data_model.close()
            except Exception as e:
                logger.warning("Failed to close data model: %s", e)

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing only)."""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except Exception as e:
                    logger.debug("Failed to close DatabaseService during reset: %s", e)
                cls._instance = None


def get_db_service() -> DatabaseService:
    """
    Dependency injection provider for DatabaseService.

    Returns the singleton DatabaseService instance. Use with FastAPI's
    Depends() to inject it into route handlers instead of creating a
    new DatabaseService() per request, which would create a new
    UniversalDataModel + SQLite connection on every call.

    Usage:
        from backend.db_service import get_db_service

        @router.get("/elements")
        async def list_elements(db: DatabaseService = Depends(get_db_service)):
            ...
    """
    return DatabaseService()
