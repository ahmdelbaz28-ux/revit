"""core/tests/test_database.py — Comprehensive unit tests for core/database.py

Tests the UniversalDataModel SQLite store covering:
- Database initialization (in-memory and file-based)
- Element CRUD operations (add, get, update, delete)
- Batch operations
- Indexed queries (by type, by project)
- Relationship operations
- Conflict detection and resolution
- Statistics endpoint
- Context manager protocol
- Deserialization (_dict_to_element)
- Edge cases and error handling
"""

import json
import os

import pytest

from core.database import UniversalDataModel, _ElementLike
from core.models import (
    ChangeSource,
    ConflictType,
    ElementType,
    Geometry,
    Point3D,
    SemanticProperties,
    UniversalElement,
)

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def udm() -> UniversalDataModel:
    """Create an in-memory UniversalDataModel instance for testing."""
    model = UniversalDataModel(db_path=":memory:")
    yield model
    model.close()


@pytest.fixture
def sample_element() -> UniversalElement:
    """Create a sample UniversalElement for testing."""
    return UniversalElement(
        element_id="elem-001",
        properties=SemanticProperties(
            element_type=ElementType.WALL,
            name=" Exterior Wall",
            material="concrete",
            fire_rating="2HR",
            height=3.5,
            width=0.25,
            load_bearing=True,
        ),
        geometry=Geometry(
            points=(
                Point3D(x=0.0, y=0.0, z=0.0),
                Point3D(x=5.0, y=0.0, z=0.0),
                Point3D(x=5.0, y=3.5, z=0.0),
                Point3D(x=0.0, y=3.5, z=0.0),
            ),
            polyline_closed=True,
        ),
        source_file="floor_plan.dwg",
        last_modified_by="autocad",
        autocad_handle="1A2B",
        revit_element_id=12345,
        project_id="proj-alpha",
    )


@pytest.fixture
def sample_element_2() -> UniversalElement:
    """Create a second sample element for testing."""
    return UniversalElement(
        element_id="elem-002",
        properties=SemanticProperties(
            element_type=ElementType.DOOR,
            name="Main Door",
            material="steel",
            fire_rating="1.5HR",
            height=2.1,
            width=0.9,
        ),
        source_file="floor_plan.rvt",
        last_modified_by="revit",
        autocad_handle="3C4D",
        project_id="proj-alpha",
    )


@pytest.fixture
def sample_element_3() -> UniversalElement:
    """Create a third sample element for a different project."""
    return UniversalElement(
        element_id="elem-003",
        properties=SemanticProperties(
            element_type=ElementType.WINDOW,
            name="Bay Window",
            material="aluminum",
            height=1.5,
            width=2.0,
        ),
        source_file="elevation.dwg",
        project_id="proj-beta",
    )


# ── Initialization Tests ───────────────────────────────────────────────────


class TestUniversalDataModelInit:
    """Tests for database initialization and configuration."""

    def test_in_memory_initialization(self, udm: UniversalDataModel):
        """Test that an in-memory database initializes correctly."""
        assert udm._db_path == ":memory:"
        assert udm._conn is not None

    def test_file_based_initialization(self, tmp_path):
        """Test that a file-based database initializes and creates directory."""
        db_file = str(tmp_path / "test_udm.db")
        model = UniversalDataModel(db_path=db_file)
        assert model._db_path == db_file
        assert os.path.exists(db_file)
        model.close()
        os.unlink(db_file)

    def test_creates_directory_for_file_db(self, tmp_path):
        """Test that directory is created for file-based databases."""
        db_dir = str(tmp_path / "nested" / "dir")
        db_file = os.path.join(db_dir, "test.db")
        model = UniversalDataModel(db_path=db_file)
        assert os.path.isdir(db_dir)
        model.close()
        os.unlink(db_file)

    def test_wal_mode_enabled(self, tmp_path):
        """Test that WAL journal mode is set for file-based databases.

        Note: In-memory databases use 'memory' mode, so we test with a file.
        """
        db_file = str(tmp_path / "wal_test.db")
        model = UniversalDataModel(db_path=db_file)
        cursor = model._conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        model.close()
        os.unlink(db_file)
        assert mode.lower() == "wal"

    def test_memory_db_journal_mode(self, udm: UniversalDataModel):
        """Test that in-memory databases use 'memory' journal mode."""
        cursor = udm._conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "memory"

    def test_foreign_keys_enabled(self, udm: UniversalDataModel):
        """Test that foreign key constraints are enabled."""
        cursor = udm._conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        fk = cursor.fetchone()[0]
        assert fk == 1

    def test_tables_created(self, udm: UniversalDataModel):
        """Test that all expected tables are created on initialization."""
        cursor = udm._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        assert "elements" in tables
        assert "relationships" in tables
        assert "conflicts" in tables

    def test_indexes_created(self, udm: UniversalDataModel):
        """Test that performance indexes are created."""
        cursor = udm._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_rel_from" in indexes
        assert "idx_rel_to" in indexes
        assert "idx_conflict_element" in indexes
        assert "idx_element_type" in indexes
        assert "idx_element_project" in indexes


# ── Context Manager Tests ──────────────────────────────────────────────────


class TestContextManager:
    """Tests for the context manager protocol."""

    def test_context_manager_enter(self):
        """Test __enter__ returns the model instance."""
        with UniversalDataModel(db_path=":memory:") as udm:
            assert isinstance(udm, UniversalDataModel)

    def test_context_manager_exit_closes(self):
        """Test __exit__ calls close() on the model."""
        model = UniversalDataModel(db_path=":memory:")
        model.__exit__(None, None, None)
        # Connection should be closed; accessing it should raise
        with pytest.raises(RuntimeError):
            model._conn.execute("SELECT 1")

    def test_close_idempotent(self, udm: UniversalDataModel):
        """Test that close() can be called multiple times without error."""
        udm.close()
        udm.close()  # Should not raise


# ── Element CRUD Tests ────────────────────────────────────────────────────


class TestAddElement:
    """Tests for the add_element method."""

    def test_add_element_success(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test adding a valid element returns True."""
        result = udm.add_element(sample_element)
        assert result is True

    def test_add_element_persists(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that an added element can be retrieved."""
        udm.add_element(sample_element)
        retrieved = udm.get_element("elem-001")
        assert retrieved is not None
        assert retrieved.element_id == "elem-001"

    def test_add_duplicate_element_returns_false(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that adding the same element twice returns False on second attempt."""
        udm.add_element(sample_element)
        result = udm.add_element(sample_element)
        assert result is False

    def test_add_element_with_minimal_fields(self, udm: UniversalDataModel):
        """Test adding an element with only the mandatory element_id."""
        elem = UniversalElement(element_id="minimal-001")
        result = udm.add_element(elem)
        assert result is True

    def test_add_element_stores_json_data(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that element data is stored as JSON in the database."""
        udm.add_element(sample_element)
        cursor = udm._conn.cursor()
        cursor.execute("SELECT data FROM elements WHERE element_id = ?", ("elem-001",))
        row = cursor.fetchone()
        assert row is not None
        data = json.loads(row["data"])
        assert data["element_id"] == "elem-001"
        assert data["source_file"] == "floor_plan.dwg"

    def test_add_element_extracts_element_type(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that element_type is extracted to the indexed column."""
        udm.add_element(sample_element)
        cursor = udm._conn.cursor()
        cursor.execute("SELECT element_type FROM elements WHERE element_id = ?", ("elem-001",))
        row = cursor.fetchone()
        assert row["element_type"] == "wall"

    def test_add_element_extracts_project_id(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that project_id is extracted to the indexed column."""
        udm.add_element(sample_element)
        cursor = udm._conn.cursor()
        cursor.execute("SELECT project_id FROM elements WHERE element_id = ?", ("elem-001",))
        row = cursor.fetchone()
        assert row["project_id"] == "proj-alpha"

    def test_add_element_with_duck_typing(self, udm: UniversalDataModel):
        """Test that add_element works with any object having element_id and to_dict()."""

        class FakeElement:
            def __init__(self):
                self.element_id = "duck-001"

            def to_dict(self):
                return {"element_id": "duck-001", "properties": {"element_type": "equipment"}}

        elem = FakeElement()
        result = udm.add_element(elem)
        assert result is True

    def test_add_element_without_properties(self, udm: UniversalDataModel):
        """Test adding element with no properties sets element_type to unknown."""
        elem = UniversalElement(element_id="no-props-001")
        udm.add_element(elem)
        cursor = udm._conn.cursor()
        cursor.execute("SELECT element_type FROM elements WHERE element_id = ?", ("no-props-001",))
        row = cursor.fetchone()
        assert row["element_type"] == "unknown"


class TestGetElement:
    """Tests for the get_element method."""

    def test_get_existing_element(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test retrieving an existing element by ID."""
        udm.add_element(sample_element)
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.element_id == "elem-001"

    def test_get_nonexistent_element(self, udm: UniversalDataModel):
        """Test retrieving a non-existent element returns None."""
        result = udm.get_element("nonexistent-id")
        assert result is None

    def test_get_element_preserves_properties(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that properties are preserved on retrieval."""
        udm.add_element(sample_element)
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.properties is not None
        assert result.properties.element_type == ElementType.WALL
        assert result.properties.name == " Exterior Wall"
        assert result.properties.material == "concrete"
        assert result.properties.fire_rating == "2HR"
        assert result.properties.height == 3.5
        assert result.properties.width == 0.25
        assert result.properties.load_bearing is True

    def test_get_element_preserves_geometry(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that geometry is preserved on retrieval."""
        udm.add_element(sample_element)
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.geometry is not None
        assert len(result.geometry.points) == 4
        assert result.geometry.polyline_closed is True

    def test_get_element_preserves_metadata(self, udm: UniversalDataModel, sample_element: UniversalElement):
        """Test that source metadata is preserved on retrieval."""
        udm.add_element(sample_element)
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.source_file == "floor_plan.dwg"
        assert result.last_modified_by == "autocad"
        assert result.autocad_handle == "1A2B"
        assert result.revit_element_id == 12345
        assert result.project_id == "proj-alpha"


class TestGetAllElements:
    """Tests for the get_all_elements method."""

    def test_get_all_empty(self, udm: UniversalDataModel):
        """Test getting elements from empty database returns empty list."""
        result = udm.get_all_elements()
        assert result == []

    def test_get_all_includes_all(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test getting all elements returns all added elements."""
        udm.add_element(sample_element)
        udm.add_element(sample_element_2)
        result = udm.get_all_elements()
        assert len(result) == 2

    def test_get_all_includes_deleted_by_default(self, udm: UniversalDataModel, sample_element):
        """Test that get_all_elements includes soft-deleted elements by default."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_all_elements()
        assert len(result) == 1
        assert result[0].is_deleted is True

    def test_get_all_excludes_deleted(self, udm: UniversalDataModel, sample_element):
        """Test that get_all_elements with include_deleted=False excludes soft-deleted."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_all_elements(include_deleted=False)
        assert len(result) == 0

    def test_get_all_mixed_deleted(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test that only active elements are returned when include_deleted=False."""
        udm.add_element(sample_element)
        udm.add_element(sample_element_2)
        udm.delete_element("elem-001")
        result = udm.get_all_elements(include_deleted=False)
        assert len(result) == 1
        assert result[0].element_id == "elem-002"


class TestUpdateElement:
    """Tests for the update_element method."""

    def test_update_element_success(self, udm: UniversalDataModel, sample_element):
        """Test updating an existing element returns True."""
        udm.add_element(sample_element)
        result = udm.update_element("elem-001", {"source_file": "updated_plan.dwg"})
        assert result is True

    def test_update_nonexistent_element(self, udm: UniversalDataModel):
        """Test updating a non-existent element returns False."""
        result = udm.update_element("nonexistent", {"source_file": "x.dwg"})
        assert result is False

    def test_update_invalid_keys_raises_valueerror(self, udm: UniversalDataModel, sample_element):
        """Test that updating with invalid keys raises ValueError (C-3 fix)."""
        udm.add_element(sample_element)
        with pytest.raises(ValueError, match="invalid keys"):
            udm.update_element("elem-001", {"evil_key": "malicious"})

    def test_update_multiple_fields(self, udm: UniversalDataModel, sample_element):
        """Test updating multiple valid fields at once."""
        udm.add_element(sample_element)
        udm.update_element("elem-001", {
            "source_file": "new_plan.dwg",
            "last_modified_by": "revit",
        })
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.source_file == "new_plan.dwg"
        assert result.last_modified_by == "revit"

    def test_update_increments_version(self, udm: UniversalDataModel, sample_element):
        """Test that updating an element increments its version."""
        udm.add_element(sample_element)
        assert udm.get_element("elem-001").version == 0
        udm.update_element("elem-001", {"source_file": "v2.dwg"})
        result = udm.get_element("elem-001")
        assert result.version == 1

    def test_update_is_deleted_field(self, udm: UniversalDataModel, sample_element):
        """Test that is_deleted is an updatable field."""
        udm.add_element(sample_element)
        udm.update_element("elem-001", {"is_deleted": True})
        result = udm.get_element("elem-001")
        assert result.is_deleted is True

    def test_update_properties_field(self, udm: UniversalDataModel, sample_element):
        """Test that properties is an updatable field."""
        udm.add_element(sample_element)
        new_props = {"element_type": "door", "name": "Updated Door"}
        udm.update_element("elem-001", {"properties": new_props})
        result = udm.get_element("elem-001")
        assert result is not None

    def test_update_project_id_field(self, udm: UniversalDataModel, sample_element):
        """Test that project_id is an updatable field."""
        udm.add_element(sample_element)
        udm.update_element("elem-001", {"project_id": "proj-gamma"})
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.project_id == "proj-gamma"

    def test_update_with_source_parameter(self, udm: UniversalDataModel, sample_element):
        """Test updating with a ChangeSource parameter for audit trail."""
        udm.add_element(sample_element)
        result = udm.update_element(
            "elem-001",
            {"source_file": "revit_updated.rvt"},
            source=ChangeSource.REVIT,
        )
        assert result is True


class TestDeleteElement:
    """Tests for the delete_element (soft-delete) method."""

    def test_delete_existing_element(self, udm: UniversalDataModel, sample_element):
        """Test soft-deleting an existing element returns True."""
        udm.add_element(sample_element)
        result = udm.delete_element("elem-001")
        assert result is True

    def test_delete_nonexistent_element(self, udm: UniversalDataModel):
        """Test soft-deleting a non-existent element returns False."""
        result = udm.delete_element("nonexistent")
        assert result is False

    def test_soft_delete_marks_is_deleted(self, udm: UniversalDataModel, sample_element):
        """Test that soft-delete sets is_deleted flag to True."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.is_deleted is True

    def test_soft_delete_preserves_data(self, udm: UniversalDataModel, sample_element):
        """Test that soft-deleted element data is still retrievable."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_element("elem-001")
        assert result is not None
        assert result.element_id == "elem-001"
        assert result.source_file == "floor_plan.dwg"

    def test_delete_with_source_parameter(self, udm: UniversalDataModel, sample_element):
        """Test soft-deleting with a ChangeSource parameter."""
        udm.add_element(sample_element)
        result = udm.delete_element("elem-001", source=ChangeSource.MANUAL)
        assert result is True


# ── Batch Operations Tests ─────────────────────────────────────────────────


class TestBatchOperations:
    """Tests for the add_elements_batch method."""

    def test_batch_add_success(self, udm: UniversalDataModel, sample_element, sample_element_2, sample_element_3):
        """Test adding multiple elements in a batch."""
        elements = [sample_element, sample_element_2, sample_element_3]
        count = udm.add_elements_batch(elements)
        assert count == 3

    def test_batch_add_empty_list(self, udm: UniversalDataModel):
        """Test batch adding an empty list returns 0."""
        count = udm.add_elements_batch([])
        assert count == 0

    def test_batch_add_duplicate_handling(self, udm: UniversalDataModel, sample_element):
        """Test that duplicates in batch are handled (INSERT OR IGNORE)."""
        udm.add_element(sample_element)
        count = udm.add_elements_batch([sample_element])
        assert count == 0

    def test_batch_add_mixed_duplicates(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test batch with some duplicates: only new elements are added."""
        udm.add_element(sample_element)
        count = udm.add_elements_batch([sample_element, sample_element_2])
        assert count == 1

    def test_batch_elements_retrievable(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test that batch-added elements can be individually retrieved."""
        udm.add_elements_batch([sample_element, sample_element_2])
        assert udm.get_element("elem-001") is not None
        assert udm.get_element("elem-002") is not None


# ── Indexed Query Tests ───────────────────────────────────────────────────


class TestGetElementsByType:
    """Tests for the get_elements_by_type method (V129 indexed query)."""

    def test_get_by_type_wall(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test filtering elements by type 'wall'."""
        udm.add_element(sample_element)  # WALL
        udm.add_element(sample_element_2)  # DOOR
        result = udm.get_elements_by_type("wall")
        assert len(result) == 1
        assert result[0].element_id == "elem-001"

    def test_get_by_type_door(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test filtering elements by type 'door'."""
        udm.add_element(sample_element)  # WALL
        udm.add_element(sample_element_2)  # DOOR
        result = udm.get_elements_by_type("door")
        assert len(result) == 1
        assert result[0].element_id == "elem-002"

    def test_get_by_type_no_match(self, udm: UniversalDataModel, sample_element):
        """Test filtering by a type that doesn't exist returns empty list."""
        udm.add_element(sample_element)
        result = udm.get_elements_by_type("roof")
        assert result == []

    def test_get_by_type_excludes_deleted(self, udm: UniversalDataModel, sample_element):
        """Test that get_elements_by_type excludes soft-deleted by default."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_elements_by_type("wall")
        assert result == []

    def test_get_by_type_includes_deleted(self, udm: UniversalDataModel, sample_element):
        """Test that get_elements_by_type with include_deleted=True includes soft-deleted."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_elements_by_type("wall", include_deleted=True)
        assert len(result) == 1

    def test_get_by_type_empty_db(self, udm: UniversalDataModel):
        """Test querying an empty database returns empty list."""
        result = udm.get_elements_by_type("wall")
        assert result == []


class TestGetElementsByProject:
    """Tests for the get_elements_by_project method (V129 indexed query)."""

    def test_get_by_project_alpha(self, udm: UniversalDataModel, sample_element, sample_element_2, sample_element_3):
        """Test filtering elements by project 'proj-alpha'."""
        udm.add_element(sample_element)  # proj-alpha
        udm.add_element(sample_element_2)  # proj-alpha
        udm.add_element(sample_element_3)  # proj-beta
        result = udm.get_elements_by_project("proj-alpha")
        assert len(result) == 2

    def test_get_by_project_beta(self, udm: UniversalDataModel, sample_element, sample_element_3):
        """Test filtering elements by project 'proj-beta'."""
        udm.add_element(sample_element)  # proj-alpha
        udm.add_element(sample_element_3)  # proj-beta
        result = udm.get_elements_by_project("proj-beta")
        assert len(result) == 1
        assert result[0].element_id == "elem-003"

    def test_get_by_project_no_match(self, udm: UniversalDataModel, sample_element):
        """Test filtering by a project that doesn't exist returns empty list."""
        udm.add_element(sample_element)
        result = udm.get_elements_by_project("nonexistent-project")
        assert result == []

    def test_get_by_project_excludes_deleted(self, udm: UniversalDataModel, sample_element):
        """Test that get_elements_by_project excludes soft-deleted by default."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_elements_by_project("proj-alpha")
        assert result == []

    def test_get_by_project_includes_deleted(self, udm: UniversalDataModel, sample_element):
        """Test that get_elements_by_project with include_deleted=True includes soft-deleted."""
        udm.add_element(sample_element)
        udm.delete_element("elem-001")
        result = udm.get_elements_by_project("proj-alpha", include_deleted=True)
        assert len(result) == 1

    def test_get_by_project_none_project(self, udm: UniversalDataModel):
        """Test querying elements that have no project_id."""
        elem = UniversalElement(element_id="no-proj-001")
        udm.add_element(elem)
        # Element with project_id=None should not appear under any project
        result = udm.get_elements_by_project("proj-alpha")
        assert result == []


# ── Conflict Detection Tests ───────────────────────────────────────────────


class TestConflictDetection:
    """Tests for the detect_conflicts method."""

    def test_no_conflicts_empty_db(self, udm: UniversalDataModel):
        """Test that an empty database has no conflicts."""
        conflicts = udm.detect_conflicts()
        assert conflicts == []

    def test_no_conflicts_single_element(self, udm: UniversalDataModel, sample_element):
        """Test that a single element produces no conflicts."""
        udm.add_element(sample_element)
        conflicts = udm.detect_conflicts()
        assert conflicts == []

    def test_conflicts_from_same_handle(self, udm: UniversalDataModel):
        """Test that elements sharing the same autocad_handle produce conflicts."""
        elem1 = UniversalElement(
            element_id="dup-001",
            properties=SemanticProperties(element_type=ElementType.WALL, name="Wall A"),
            autocad_handle="SHARED_HANDLE",
            source_file="a.dwg",
        )
        elem2 = UniversalElement(
            element_id="dup-002",
            properties=SemanticProperties(element_type=ElementType.WALL, name="Wall B"),
            autocad_handle="SHARED_HANDLE",
            source_file="b.rvt",
        )
        udm.add_element(elem1)
        udm.add_element(elem2)
        conflicts = udm.detect_conflicts()
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == ConflictType.PROPERTY_CONFLICT

    def test_conflicts_excludes_deleted(self, udm: UniversalDataModel):
        """Test that soft-deleted elements are not considered in conflict detection."""
        elem1 = UniversalElement(
            element_id="del-001",
            properties=SemanticProperties(element_type=ElementType.WALL, name="Wall"),
            autocad_handle="HANDLE_X",
        )
        elem2 = UniversalElement(
            element_id="del-002",
            properties=SemanticProperties(element_type=ElementType.WALL, name="Wall"),
            autocad_handle="HANDLE_X",
        )
        udm.add_element(elem1)
        udm.add_element(elem2)
        udm.delete_element("del-001")
        # Only one non-deleted element with HANDLE_X — no conflict
        conflicts = udm.detect_conflicts()
        # The deleted element is excluded, so no conflict from duplicate handle
        handle_conflicts = [c for c in conflicts if c.element_id in ("del-001", "del-002")]
        assert len(handle_conflicts) == 0


class TestResolveConflict:
    """Tests for the resolve_conflict method."""

    def test_resolve_nonexistent_conflict(self, udm: UniversalDataModel):
        """Test resolving a non-existent conflict returns None."""
        result = udm.resolve_conflict("nonexistent-conflict")
        assert result is None

    def test_resolve_persisted_conflict(self, udm: UniversalDataModel, sample_element):
        """Test resolving a conflict that exists in the conflicts table."""
        # Add element first to satisfy foreign key constraint
        udm.add_element(sample_element)

        # Manually insert a conflict
        cursor = udm._conn.cursor()
        cursor.execute(
            "INSERT INTO conflicts (conflict_id, element_id, conflict_type, source_a, source_b, change_a, change_b, resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("conflict-001", "elem-001", "geometry_mismatch", "autocad", "revit",
             json.dumps({"x": 1.0}), json.dumps({"x": 2.0}), 0),
        )
        udm._conn.commit()

        result = udm.resolve_conflict("conflict-001", strategy="SEMANTIC_MERGE")
        assert result is not None
        assert result.conflict_id == "conflict-001"
        assert result.resolved is True
        assert result.resolution == {"strategy": "SEMANTIC_MERGE"}

    def test_resolve_with_last_write_wins(self, udm: UniversalDataModel, sample_element_2):
        """Test resolving a conflict with LAST_WRITE_WINS strategy."""
        # Add element first to satisfy foreign key constraint
        udm.add_element(sample_element_2)

        cursor = udm._conn.cursor()
        cursor.execute(
            "INSERT INTO conflicts (conflict_id, element_id, conflict_type, resolved) VALUES (?, ?, ?, ?)",
            ("conflict-002", "elem-002", "property_conflict", 0),
        )
        udm._conn.commit()

        result = udm.resolve_conflict("conflict-002", strategy="LAST_WRITE_WINS")
        assert result is not None
        assert result.resolved is True

    def test_resolve_marks_conflict_in_db(self, udm: UniversalDataModel, sample_element_3):
        """Test that resolving a conflict updates the database."""
        # Add element first to satisfy foreign key constraint
        udm.add_element(sample_element_3)

        cursor = udm._conn.cursor()
        cursor.execute(
            "INSERT INTO conflicts (conflict_id, element_id, conflict_type, resolved) VALUES (?, ?, ?, ?)",
            ("conflict-003", "elem-003", "deletion_conflict", 0),
        )
        udm._conn.commit()

        udm.resolve_conflict("conflict-003")
        cursor.execute("SELECT resolved FROM conflicts WHERE conflict_id = ?", ("conflict-003",))
        row = cursor.fetchone()
        assert row["resolved"] == 1


# ── Statistics Tests ───────────────────────────────────────────────────────


class TestGetStatistics:
    """Tests for the get_statistics method."""

    def test_statistics_empty_db(self, udm: UniversalDataModel):
        """Test statistics on an empty database."""
        stats = udm.get_statistics()
        assert stats.total_elements == 0
        assert stats.active_elements == 0
        assert stats.deleted_elements == 0
        assert stats.total_connections == 0
        assert stats.total_conflicts == 0
        assert stats.unresolved_conflicts == 0

    def test_statistics_with_elements(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test statistics after adding elements."""
        udm.add_element(sample_element)
        udm.add_element(sample_element_2)
        stats = udm.get_statistics()
        assert stats.total_elements == 2
        assert stats.active_elements == 2
        assert stats.deleted_elements == 0

    def test_statistics_after_deletion(self, udm: UniversalDataModel, sample_element, sample_element_2):
        """Test statistics after soft-deleting an element."""
        udm.add_element(sample_element)
        udm.add_element(sample_element_2)
        udm.delete_element("elem-001")
        stats = udm.get_statistics()
        assert stats.total_elements == 2
        assert stats.active_elements == 1
        assert stats.deleted_elements == 1

    def test_statistics_with_conflicts(self, udm: UniversalDataModel):
        """Test statistics with persisted conflicts."""
        # Add elements first to satisfy foreign key constraints
        elem1 = UniversalElement(element_id="e1", properties=SemanticProperties(element_type=ElementType.WALL))
        elem2 = UniversalElement(element_id="e2", properties=SemanticProperties(element_type=ElementType.DOOR))
        udm.add_element(elem1)
        udm.add_element(elem2)

        cursor = udm._conn.cursor()
        cursor.execute(
            "INSERT INTO conflicts (conflict_id, element_id, conflict_type, resolved) VALUES (?, ?, ?, ?)",
            ("c1", "e1", "geometry_mismatch", 0),
        )
        cursor.execute(
            "INSERT INTO conflicts (conflict_id, element_id, conflict_type, resolved) VALUES (?, ?, ?, ?)",
            ("c2", "e2", "property_conflict", 1),
        )
        udm._conn.commit()
        stats = udm.get_statistics()
        assert stats.total_conflicts == 2
        assert stats.unresolved_conflicts == 1


# ── Deserialization Tests ──────────────────────────────────────────────────


class TestDictToElement:
    """Tests for the _dict_to_element static method."""

    def test_dict_to_element_full(self):
        """Test deserializing a full element dictionary."""
        data = {
            "element_id": "test-001",
            "properties": {
                "element_type": "wall",
                "name": "Test Wall",
                "material": "concrete",
                "fire_rating": "2HR",
                "height": 3.0,
                "width": 0.2,
                "load_bearing": True,
            },
            "geometry": {
                "points": [{"x": 0.0, "y": 0.0, "z": 0.0}, {"x": 5.0, "y": 0.0, "z": 0.0}],
                "polyline_closed": False,
            },
            "relationships": [
                {"from_element_id": "test-001", "to_element_id": "test-002", "relationship_type": "adjacent"},
            ],
            "source_file": "test.dwg",
            "last_modified_by": "autocad",
            "autocad_handle": "ABC",
            "revit_element_id": 999,
            "created_timestamp": "2024-01-01T00:00:00+00:00",
            "last_modified_timestamp": "2024-06-01T00:00:00+00:00",
            "version": 3,
            "is_deleted": False,
            "project_id": "proj-001",
        }
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert result.element_id == "test-001"
        assert result.properties is not None
        assert result.properties.element_type == ElementType.WALL
        assert result.geometry is not None
        assert len(result.geometry.points) == 2
        assert len(result.relationships) == 1
        assert result.source_file == "test.dwg"
        assert result.version == 3

    def test_dict_to_element_minimal(self):
        """Test deserializing an element with minimal data."""
        data = {"element_id": "min-001"}
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert result.element_id == "min-001"
        assert result.properties is None
        assert result.geometry is None

    def test_dict_to_element_with_version_override(self):
        """Test that version parameter overrides data version."""
        data = {"element_id": "v-001", "version": 5}
        result = UniversalDataModel._dict_to_element(data, version=10)
        assert result is not None
        assert result.version == 10

    def test_dict_to_element_with_is_deleted_override(self):
        """Test that is_deleted parameter is respected."""
        data = {"element_id": "d-001", "is_deleted": False}
        result = UniversalDataModel._dict_to_element(data, is_deleted=True)
        assert result is not None
        assert result.is_deleted is True

    def test_dict_to_element_unknown_element_type(self):
        """Test that an unknown element_type is kept as string."""
        data = {
            "element_id": "unk-001",
            "properties": {"element_type": "custom_type", "name": "Custom"},
        }
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert result.properties is not None
        # Should fall back to string since "custom_type" is not in ElementType
        assert isinstance(result.properties.element_type, str) or hasattr(result.properties.element_type, 'value')

    def test_dict_to_element_with_relationships(self):
        """Test deserializing with multiple relationships."""
        data = {
            "element_id": "rel-001",
            "relationships": [
                {"from_element_id": "rel-001", "to_element_id": "rel-002", "relationship_type": "contains"},
                {"from_element_id": "rel-001", "to_element_id": "rel-003", "relationship_type": "adjacent"},
            ],
        }
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert len(result.relationships) == 2
        assert result.relationships[0].relationship_type == "contains"
        assert result.relationships[1].relationship_type == "adjacent"

    def test_dict_to_element_with_malformed_timestamp(self):
        """Test that malformed timestamps default to None without error."""
        data = {
            "element_id": "ts-001",
            "created_timestamp": "not-a-date",
            "last_modified_timestamp": "also-not-a-date",
        }
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert result.created_timestamp is None
        assert result.last_modified_timestamp is None

    def test_dict_to_element_with_geometry_points(self):
        """Test that geometry points are correctly deserialized."""
        data = {
            "element_id": "geom-001",
            "geometry": {
                "points": [
                    {"x": 1.0, "y": 2.0, "z": 3.0},
                    {"x": 4.0, "y": 5.0, "z": 6.0},
                    {"x": 7.0, "y": 8.0, "z": 9.0},
                ],
                "polyline_closed": True,
            },
        }
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert result.geometry is not None
        assert len(result.geometry.points) == 3
        assert result.geometry.points[0].x == 1.0
        assert result.geometry.points[1].y == 5.0
        assert result.geometry.points[2].z == 9.0


# ── Protocol Tests ─────────────────────────────────────────────────────────


class TestElementLikeProtocol:
    """Tests for the _ElementLike protocol."""

    def test_universal_element_satisfies_protocol(self, sample_element):
        """Test that UniversalElement satisfies _ElementLike protocol."""
        assert isinstance(sample_element, _ElementLike)

    def test_duck_typed_element_satisfies_protocol(self):
        """Test that a duck-typed object satisfies _ElementLike protocol."""

        class FakeElement:
            element_id = "fake-001"

            def to_dict(self):
                return {"element_id": "fake-001"}

        assert isinstance(FakeElement(), _ElementLike)


# ── Round-trip Serialization Tests ─────────────────────────────────────────


class TestRoundTrip:
    """Tests verifying that elements survive a full add→get cycle."""

    def test_round_trip_with_all_fields(self, udm: UniversalDataModel, sample_element):
        """Test that an element with all fields survives add→get round trip."""
        udm.add_element(sample_element)
        retrieved = udm.get_element("elem-001")
        assert retrieved is not None
        assert retrieved.element_id == sample_element.element_id
        assert retrieved.source_file == sample_element.source_file
        assert retrieved.autocad_handle == sample_element.autocad_handle
        assert retrieved.revit_element_id == sample_element.revit_element_id
        assert retrieved.project_id == sample_element.project_id

    def test_round_trip_preserves_geometry(self, udm: UniversalDataModel, sample_element):
        """Test that geometry survives add→get round trip."""
        udm.add_element(sample_element)
        retrieved = udm.get_element("elem-001")
        assert retrieved is not None
        assert retrieved.geometry is not None
        assert len(retrieved.geometry.points) == len(sample_element.geometry.points)
        for orig, got in zip(sample_element.geometry.points, retrieved.geometry.points, strict=False):
            assert abs(orig.x - got.x) < 1e-9
            assert abs(orig.y - got.y) < 1e-9
            assert abs(orig.z - got.z) < 1e-9

    def test_to_dict_round_trip(self, sample_element):
        """Test that to_dict() output can be deserialized correctly."""
        data = sample_element.to_dict()
        result = UniversalDataModel._dict_to_element(data)
        assert result is not None
        assert result.element_id == sample_element.element_id
