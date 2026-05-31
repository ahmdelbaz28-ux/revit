"""
FireAI Digital Twin - Database Service
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
from typing import Any, Dict, List, Optional, Tuple

from core.database import UniversalDataModel
from core.models import (
    ChangeSource,
    Conflict,
    ConflictType,
    Geometry,
    Point3D,
    Relationship,
    SemanticProperties,
    UniversalElement,
)

from backend.schemas import (
    ConnectionCreate,
    ConnectionResponse,
    ConflictResponse,
    ElementCreate,
    ElementResponse,
    ElementUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    StatisticsResponse,
)

logger = logging.getLogger(__name__)


def _normalize_sort(sort_by: str) -> str:
    """Convert camelCase sort parameter to snake_case."""
    import re
    # Insert underscore before uppercase letters and lowercase
    result = re.sub(r'([A-Z])', r'_\1', sort_by).lower()
    # Remove leading underscore if present
    return result.lstrip('_')


class DatabaseService:
    """
    Thread-safe singleton that wraps UniversalDataModel and adds project support.

    Provides methods that the routers can call, handling the conversion between
    Pydantic schemas and core dataclasses.
    """

    _instance: Optional[DatabaseService] = None
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

    def __init__(self, db_path: Optional[str] = None) -> None:
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
        self._projects: Dict[str, Dict[str, Any]] = {}
        self._load_projects_from_db()

        self._initialized = True
        logger.info(f"DatabaseService initialized with db_path={db_path}")

    # ──────────────────────────────────────────────────────────────────────────
    # Projects table initialization
    # ──────────────────────────────────────────────────────────────────────────

    def _safe_db_execute(self, sql: str, params: tuple = (), commit: bool = False) -> Optional[Any]:
        """Execute SQL on the UDM connection with proper lock acquisition.

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
        """Get database connection ONLY while holding the database lock.

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
        """Get the database lock for multi-statement operations.

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
                cursor = self._safe_db_execute('''
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
                logger.error(f"Error initializing projects table: {e}")

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
                logger.info(f"Loaded {len(self._projects)} projects from database")
            except Exception as e:
                logger.error(f"Error loading projects: {e}")

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
                logger.error(f"Error persisting project: {e}")
                raise

            # Cache in memory
            self._projects[project_id] = project_dict

            return self._project_to_response(project_dict)

    def get_project(self, project_id: str) -> Optional[ProjectResponse]:
        """Get a project by ID."""
        with self._service_lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            return self._project_to_response(project)

    def list_projects(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_timestamp",
        sort_order: str = "desc",
    ) -> Tuple[List[ProjectResponse], int]:
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

    def update_project(self, project_id: str, update_data: ProjectUpdate) -> Optional[ProjectResponse]:
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
                logger.error(f"Error updating project: {e}")
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
                logger.error(f"Error deleting project: {e}")
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
                except Exception:
                    pass

            # Remove from cache
            del self._projects[project_id]
            return True

    def _project_to_response(self, project_dict: Dict[str, Any]) -> ProjectResponse:
        """Convert project dict to ProjectResponse."""
        # Count elements for this project
        element_count = 0
        try:
            element_count = self._count_project_elements(project_dict["project_id"])
        except Exception:
            pass

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

    def _get_element_project_id(self, element_id: str) -> Optional[str]:
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

    def get_element(self, element_id: str) -> Optional[ElementResponse]:
        """Get an element by ID."""
        with self._service_lock:
            element = self._data_model.get_element(element_id)
            if element is None:
                return None
            project_id = self._get_element_project_id(element_id)
            return self._element_to_response(element, project_id)

    def list_elements(
        self,
        element_type: Optional[str] = None,
        project_id: Optional[str] = None,
        is_deleted: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_timestamp",
        sort_order: str = "desc",
    ) -> Tuple[List[ElementResponse], int]:
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
                except Exception:
                    pass
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

    def update_element(self, element_id: str, update_data: ElementUpdate) -> Optional[ElementResponse]:
        """Update an element."""
        with self._service_lock:
            element = self._data_model.get_element(element_id)
            if element is None:
                return None

            # Build updates dict for UniversalDataModel.update_element()
            updates: Dict[str, Any] = {}

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
                    except ValueError:
                        pass
                self._data_model.delete_element(element_id, source=source)
            elif updates:
                source = ChangeSource.MANUAL
                if update_data.last_modified_by:
                    try:
                        source = ChangeSource(update_data.last_modified_by)
                    except ValueError:
                        pass
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

    def _element_to_response(self, element: UniversalElement, project_id: Optional[str] = None) -> ElementResponse:
        """Convert UniversalElement to ElementResponse."""
        props_response = None
        if element.properties:
            props_response = {
                "element_type": element.properties.element_type.value if hasattr(element.properties.element_type, 'value') else str(element.properties.element_type),
                "name": element.properties.name,
                "description": element.properties.description,
                "material": element.properties.material,
                "fire_rating": element.properties.fire_rating,
                "height": element.properties.height,
                "width": element.properties.width,
                "load_bearing": element.properties.load_bearing,
                "layer": element.properties.layer,
                "revit_category": element.properties.revit_category,
            }

        geom_response = None
        if element.geometry:
            geom_response = {
                "points": [{"x": p.x, "y": p.y, "z": p.z} for p in element.geometry.points],
                "polyline_closed": element.geometry.polyline_closed,
                "area": element.geometry.area,
                "perimeter": element.geometry.perimeter,
            }

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
        """Associate an element with a project.

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
                logger.error(f"Error associating element with project: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Connection (Relationship) CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def create_connection(self, data: ConnectionCreate) -> ConnectionResponse:
        """Create a new connection (relationship) between elements."""
        with self._service_lock:
            connection_id = str(uuid.uuid4())

            # Verify both elements exist
            from_element = self._data_model.get_element(data.from_element_id)
            to_element = self._data_model.get_element(data.to_element_id)

            if from_element is None:
                raise ValueError(f"Element {data.from_element_id} not found")
            if to_element is None:
                raise ValueError(f"Element {data.to_element_id} not found")

            # Create relationship object
            relationship = Relationship(
                from_element_id=data.from_element_id,
                to_element_id=data.to_element_id,
                relationship_type=data.relationship_type,
                is_parametric=data.is_parametric,
                metadata=data.metadata,
            )

            # Add to from_element's relationships
            from_element.relationships.append(relationship)

            # Also add reverse relationship for easy traversal
            reverse_rel = Relationship(
                from_element_id=data.to_element_id,
                to_element_id=data.from_element_id,
                relationship_type=f"reverse_{data.relationship_type}",
                is_parametric=data.is_parametric,
                metadata=data.metadata,
            )
            to_element.relationships.append(reverse_rel)

            # Relationships are already updated in-memory via .append() above
            # No need to call update_element — it would convert Relationship objects to dicts
            # which breaks subsequent to_dict() calls on the element.
            # The relationships table is updated separately below.

            # Persist to relationships table
            # BUG-37 FIX: If SQL INSERT fails, the in-memory state must be rolled back.
            # Previously, in-memory .append() succeeded but SQL failed silently, causing
            # connections to disappear on restart. Now we raise on SQL failure.
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
                # BUG-37 FIX: Roll back in-memory changes on SQL failure
                from_element.relationships.pop()
                to_element.relationships.pop()
                logger.error(f"Error persisting connection: {e}")
                raise RuntimeError(f"Failed to persist connection: {e}")

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
        project_id: Optional[str] = None,
        element_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ConnectionResponse], int]:
        """List connections with optional filtering and pagination."""
        with self._service_lock:
            connections: List[ConnectionResponse] = []

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

                cursor = self._safe_db_execute(query, params)
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
                logger.error(f"Error listing connections: {e}")
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
                except Exception:
                    pass
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
        """Delete a connection by ID.

        Removes the relationship from both the SQL table AND the in-memory
        element.relationships lists. Also removes the reverse relationship
        that was appended to to_element.relationships at creation time.
        """
        with self._service_lock:
            try:
                with self._db_lock:
                    conn = self._db_conn
                cursor = conn.cursor()

                # Fetch the relationship details before deleting so we can
                # clean up in-memory state on both elements.
                cursor.execute(
                    "SELECT from_element_id, to_element_id, relationship_type "
                    "FROM relationships WHERE relationship_id=?",
                    (connection_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False

                from_eid = row[0]
                to_eid = row[1]
                rel_type = row[2]

                # Delete from SQL
                cursor.execute(
                    "DELETE FROM relationships WHERE relationship_id=?",
                    (connection_id,),
                )
                conn.commit()

                # Remove from in-memory element.relationships
                from_element = self._data_model.elements.get(from_eid)
                if from_element:
                    from_element.relationships = [
                        r for r in from_element.relationships
                        if not (r.from_element_id == from_eid
                                and r.to_element_id == to_eid
                                and r.relationship_type == rel_type)
                    ]

                to_element = self._data_model.elements.get(to_eid)
                if to_element:
                    reverse_type = f"reverse_{rel_type}"
                    to_element.relationships = [
                        r for r in to_element.relationships
                        if not (r.from_element_id == to_eid
                                and r.to_element_id == from_eid
                                and r.relationship_type == reverse_type)
                    ]

                return True
            except Exception as e:
                logger.error(f"Error deleting connection: {e}")
                return False

    # ──────────────────────────────────────────────────────────────────────────
    # Conflict detection and resolution
    # ──────────────────────────────────────────────────────────────────────────

    def detect_conflicts(self) -> List[ConflictResponse]:
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
        resolved: Optional[bool] = None,
        conflict_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ConflictResponse], int]:
        """List conflicts with optional filtering and pagination."""
        with self._service_lock:
            conflicts = list(self._data_model.conflicts.values())

            # Also run detection to pick up new conflicts
            new_conflicts = self._data_model.detect_conflicts()
            for c in new_conflicts:
                if c.conflict_id not in self._data_model.conflicts:
                    self._data_model.conflicts[c.conflict_id] = c

            all_conflicts = list(self._data_model.conflicts.values())

            # Filter
            if resolved is not None:
                all_conflicts = [c for c in all_conflicts if c.resolved == resolved]
            if conflict_type:
                all_conflicts = [c for c in all_conflicts if c.conflict_type.value == conflict_type]

            total = len(all_conflicts)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = all_conflicts[start:end]

            responses = [
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
                for c in paginated
            ]

            return responses, total

    def resolve_conflict(self, conflict_id: str, strategy: str = "SEMANTIC_MERGE") -> Optional[ConflictResponse]:
        """Resolve a conflict by ID."""
        with self._service_lock:
            conflict = self._data_model.conflicts.get(conflict_id)
            if conflict is None:
                return None

            success = self._data_model.resolve_conflict(conflict, strategy=strategy)
            if not success:
                raise RuntimeError(f"Failed to resolve conflict {conflict_id}")

            # Apply resolution to element if possible
            if conflict.resolution and conflict.element_id:
                element = self._data_model.get_element(conflict.element_id)
                if element:
                    self._data_model.update_element(
                        conflict.element_id,
                        conflict.resolution,
                        source=ChangeSource.MANUAL,
                        reason=f"Conflict resolution: {conflict_id}",
                    )

            return ConflictResponse(
                conflict_id=conflict.conflict_id,
                element_id=conflict.element_id,
                conflict_type=conflict.conflict_type.value,
                timestamp=conflict.timestamp.isoformat() if conflict.timestamp else None,
                source_a=conflict.source_a.value,
                source_b=conflict.source_b.value,
                change_a=conflict.change_a,
                change_b=conflict.change_b,
                resolution=conflict.resolution,
                resolved=conflict.resolved,
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
            total_conflicts = len(self._data_model.conflicts)
            unresolved_conflicts = sum(
                1 for c in self._data_model.conflicts.values() if not c.resolved
            )

            return StatisticsResponse(
                total_elements=stats["total_elements"],
                deleted_elements=stats["deleted_elements"],
                active_elements=stats["active_elements"],
                total_projects=total_projects,
                active_projects=active_projects,
                total_connections=total_connections,
                total_conflicts=total_conflicts,
                unresolved_conflicts=unresolved_conflicts,
                pending_autocad_to_revit=stats["pending_autocad_to_revit"],
                pending_revit_to_autocad=stats["pending_revit_to_autocad"],
                database_version=stats["database_version"],
                last_sync=stats.get("last_sync"),
            )

    def export_data(
        self,
        project_id: Optional[str] = None,
        element_types: Optional[List[str]] = None,
        include_deleted: bool = False,
    ) -> Dict[str, Any]:
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
                except Exception:
                    pass
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
            except Exception:
                pass

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
            except Exception:
                pass

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing only)."""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except Exception:
                    pass
                cls._instance = None
