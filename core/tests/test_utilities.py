"""core/tests/test_utilities.py — Comprehensive unit tests for core/models.py

Tests the core utility and model classes covering:
- Point3D: creation, validation, immutability
- Geometry: area calculation (Shoelace), perimeter calculation, edge cases
- SemanticProperties: creation, validation, serialization (to_dict)
- Relationship: creation, serialization (to_dict)
- Conflict: creation, immutability, ConflictType enum
- UniversalElement: creation, mandatory element_id, to_dict serialization
- ElementType, ChangeSource, ConflictType enumerations
- Edge cases: NaN/Inf rejection, negative dimension rejection, frozen immutability
"""

import math
from datetime import datetime, timezone

import pytest

from core.models import (
    ChangeSource,
    Conflict,
    ConflictType,
    ElementType,
    Geometry,
    Point3D,
    Relationship,
    SemanticProperties,
    UniversalElement,
)

# ═══════════════════════════════════════════════════════════════════════════
# Point3D Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPoint3D:
    """Tests for the Point3D frozen dataclass."""

    def test_create_point_with_xyz(self):
        """Test creating a Point3D with explicit x, y, z."""
        p = Point3D(x=1.0, y=2.0, z=3.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0

    def test_create_point_z_default_zero(self):
        """Test that z defaults to 0.0 when not provided."""
        p = Point3D(x=1.0, y=2.0)
        assert p.z == 0.0

    def test_create_point_at_origin(self):
        """Test creating a point at the origin."""
        p = Point3D(x=0.0, y=0.0, z=0.0)
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0

    def test_create_point_negative_coordinates(self):
        """Test that negative coordinates are allowed (valid in BIM)."""
        p = Point3D(x=-1.5, y=-2.0, z=-3.0)
        assert p.x == -1.5
        assert p.y == -2.0
        assert p.z == -3.0

    def test_reject_nan_x(self):
        """Test that NaN in x coordinate raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            Point3D(x=float("nan"), y=0.0, z=0.0)

    def test_reject_nan_y(self):
        """Test that NaN in y coordinate raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            Point3D(x=0.0, y=float("nan"), z=0.0)

    def test_reject_nan_z(self):
        """Test that NaN in z coordinate raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            Point3D(x=0.0, y=0.0, z=float("nan"))

    def test_reject_inf_x(self):
        """Test that +Inf in x coordinate raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            Point3D(x=float("inf"), y=0.0, z=0.0)

    def test_reject_negative_inf_y(self):
        """Test that -Inf in y coordinate raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            Point3D(x=0.0, y=float("-inf"), z=0.0)

    def test_frozen_immutability(self):
        """Test that Point3D is frozen (immutable)."""
        p = Point3D(x=1.0, y=2.0, z=3.0)
        with pytest.raises(AttributeError):
            p.x = 10.0  # type: ignore[misc]

    def test_frozen_cannot_add_attribute(self):
        """Test that new attributes cannot be added to frozen Point3D."""
        p = Point3D(x=1.0, y=2.0, z=3.0)
        with pytest.raises(AttributeError):
            p.new_field = 42  # type: ignore[attr-defined]

    def test_equality(self):
        """Test Point3D equality comparison."""
        p1 = Point3D(x=1.0, y=2.0, z=3.0)
        p2 = Point3D(x=1.0, y=2.0, z=3.0)
        assert p1 == p2

    def test_inequality(self):
        """Test Point3D inequality comparison."""
        p1 = Point3D(x=1.0, y=2.0, z=3.0)
        p2 = Point3D(x=1.0, y=2.0, z=4.0)
        assert p1 != p2

    def test_hash_consistency(self):
        """Test that equal Point3D objects have the same hash."""
        p1 = Point3D(x=1.0, y=2.0, z=3.0)
        p2 = Point3D(x=1.0, y=2.0, z=3.0)
        assert hash(p1) == hash(p2)

    def test_large_coordinates(self):
        """Test Point3D with very large but finite coordinates."""
        p = Point3D(x=1e10, y=-1e10, z=0.0)
        assert p.x == 1e10
        assert p.y == -1e10

    def test_very_small_coordinates(self):
        """Test Point3D with very small (epsilon) coordinates."""
        p = Point3D(x=1e-15, y=1e-15, z=1e-15)
        assert p.x == 1e-15
        assert math.isfinite(p.x)


# ═══════════════════════════════════════════════════════════════════════════
# Geometry Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestGeometry:
    """Tests for the Geometry frozen dataclass with cached area/perimeter."""

    def test_empty_geometry(self):
        """Test creating an empty Geometry."""
        g = Geometry()
        assert g.points == ()
        assert g.polyline_closed is False
        assert g.area == 0.0
        assert g.perimeter == 0.0

    def test_single_point_geometry(self):
        """Test geometry with a single point — no area or perimeter."""
        g = Geometry(points=(Point3D(x=1.0, y=2.0, z=0.0),))
        assert len(g.points) == 1
        assert g.area == 0.0
        assert g.perimeter == 0.0

    def test_two_point_open_polyline(self):
        """Test open polyline with two points — perimeter only."""
        g = Geometry(
            points=(Point3D(x=0.0, y=0.0), Point3D(x=3.0, y=4.0)),
            polyline_closed=False,
        )
        assert g.area == 0.0
        assert abs(g.perimeter - 5.0) < 1e-9  # 3-4-5 triangle distance

    def test_two_point_closed_polyline(self):
        """Test closed polyline with two points — round-trip perimeter (V83 fix)."""
        g = Geometry(
            points=(Point3D(x=0.0, y=0.0), Point3D(x=3.0, y=0.0)),
            polyline_closed=True,
        )
        assert g.area == 0.0  # Need >= 3 points for area
        assert abs(g.perimeter - 6.0) < 1e-9  # 3.0 + 3.0 (round-trip)

    def test_triangle_area_shoelace(self):
        """Test area calculation using Shoelace formula for a right triangle."""
        # Right triangle: (0,0), (4,0), (0,3) — area = 0.5 * 4 * 3 = 6
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=4.0, y=0.0),
                Point3D(x=0.0, y=3.0),
            ),
            polyline_closed=True,
        )
        assert abs(g.area - 6.0) < 1e-9

    def test_square_area(self):
        """Test area calculation for a unit square."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=1.0, y=0.0),
                Point3D(x=1.0, y=1.0),
                Point3D(x=0.0, y=1.0),
            ),
            polyline_closed=True,
        )
        assert abs(g.area - 1.0) < 1e-9

    def test_rectangle_area(self):
        """Test area calculation for a 5x3 rectangle."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=5.0, y=0.0),
                Point3D(x=5.0, y=3.0),
                Point3D(x=0.0, y=3.0),
            ),
            polyline_closed=True,
        )
        assert abs(g.area - 15.0) < 1e-9

    def test_open_polyline_zero_area(self):
        """Test that open polylines always have area 0.0."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=5.0, y=0.0),
                Point3D(x=5.0, y=3.0),
            ),
            polyline_closed=False,
        )
        assert g.area == 0.0

    def test_perimeter_open_polyline(self):
        """Test perimeter for an open polyline (sum of edge lengths)."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=3.0, y=0.0),
                Point3D(x=3.0, y=4.0),
            ),
            polyline_closed=False,
        )
        # Edge 1: 0→3 = 3.0, Edge 2: 3→5 = 4.0 (3-4-5 triangle vertical)
        assert abs(g.perimeter - 7.0) < 1e-9

    def test_perimeter_closed_polygon(self):
        """Test perimeter for a closed polygon (includes closing edge)."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=3.0, y=0.0),
                Point3D(x=3.0, y=4.0),
            ),
            polyline_closed=True,
        )
        # 3.0 + 4.0 + 5.0 (closing edge: 3-4-5 triangle)
        assert abs(g.perimeter - 12.0) < 1e-9

    def test_perimeter_with_z_elevation(self):
        """Test perimeter includes z-component in 3D distance."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0, z=0.0),
                Point3D(x=3.0, y=0.0, z=4.0),
            ),
            polyline_closed=False,
        )
        # 3D distance = sqrt(9 + 0 + 16) = 5.0
        assert abs(g.perimeter - 5.0) < 1e-9

    def test_frozen_immutability(self):
        """Test that Geometry is frozen (immutable)."""
        g = Geometry(points=(Point3D(x=1.0, y=2.0),))
        with pytest.raises(AttributeError):
            g.area = 999.0  # type: ignore[misc]

    def test_points_is_tuple(self):
        """Test that points is a tuple, not a list (V83 fix)."""
        g = Geometry(points=(Point3D(x=0.0, y=0.0), Point3D(x=1.0, y=1.0)))
        assert isinstance(g.points, tuple)

    def test_calculate_area_directly(self):
        """Test calling calculate_area() directly on a geometry instance."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=10.0, y=0.0),
                Point3D(x=10.0, y=10.0),
                Point3D(x=0.0, y=10.0),
            ),
            polyline_closed=True,
        )
        assert abs(g.calculate_area() - 100.0) < 1e-9

    def test_calculate_perimeter_directly(self):
        """Test calling calculate_perimeter() directly on a geometry instance."""
        g = Geometry(
            points=(
                Point3D(x=0.0, y=0.0),
                Point3D(x=10.0, y=0.0),
                Point3D(x=10.0, y=10.0),
                Point3D(x=0.0, y=10.0),
            ),
            polyline_closed=True,
        )
        assert abs(g.calculate_perimeter() - 40.0) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════
# SemanticProperties Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSemanticProperties:
    """Tests for the SemanticProperties frozen dataclass."""

    def test_create_with_all_fields(self):
        """Test creating SemanticProperties with all fields populated."""
        sp = SemanticProperties(
            element_type=ElementType.WALL,
            name="Exterior Wall",
            description="Load-bearing exterior wall",
            material="concrete",
            fire_rating="2HR",
            height=3.5,
            width=0.25,
            load_bearing=True,
            layer="A-WALL",
            revit_category="Walls",
        )
        assert sp.element_type == ElementType.WALL
        assert sp.name == "Exterior Wall"
        assert sp.description == "Load-bearing exterior wall"
        assert sp.material == "concrete"
        assert sp.fire_rating == "2HR"
        assert sp.height == 3.5
        assert sp.width == 0.25
        assert sp.load_bearing is True
        assert sp.layer == "A-WALL"
        assert sp.revit_category == "Walls"

    def test_create_with_defaults(self):
        """Test creating SemanticProperties with only mandatory field."""
        sp = SemanticProperties(element_type=ElementType.WALL)
        assert sp.name == ""
        assert sp.description is None
        assert sp.material is None
        assert sp.fire_rating is None
        assert sp.height is None
        assert sp.width is None
        assert sp.load_bearing is False
        assert sp.layer is None
        assert sp.revit_category is None

    def test_element_type_as_string(self):
        """Test that element_type can be a string (Union[ElementType, str])."""
        sp = SemanticProperties(element_type="custom_type")
        assert sp.element_type == "custom_type"

    def test_reject_nan_height(self):
        """Test that NaN height raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            SemanticProperties(element_type=ElementType.WALL, height=float("nan"))

    def test_reject_inf_height(self):
        """Test that Inf height raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            SemanticProperties(element_type=ElementType.WALL, height=float("inf"))

    def test_reject_negative_height(self):
        """Test that negative height raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            SemanticProperties(element_type=ElementType.WALL, height=-1.0)

    def test_reject_nan_width(self):
        """Test that NaN width raises ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            SemanticProperties(element_type=ElementType.WALL, width=float("nan"))

    def test_reject_negative_width(self):
        """Test that negative width raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            SemanticProperties(element_type=ElementType.WALL, width=-0.1)

    def test_zero_height_allowed(self):
        """Test that zero height is allowed (non-negative)."""
        sp = SemanticProperties(element_type=ElementType.WALL, height=0.0)
        assert sp.height == 0.0

    def test_zero_width_allowed(self):
        """Test that zero width is allowed (non-negative)."""
        sp = SemanticProperties(element_type=ElementType.WALL, width=0.0)
        assert sp.width == 0.0

    def test_frozen_immutability(self):
        """Test that SemanticProperties is frozen (immutable)."""
        sp = SemanticProperties(element_type=ElementType.WALL, name="Test")
        with pytest.raises(AttributeError):
            sp.name = "Modified"  # type: ignore[misc]

    def test_to_dict_with_enum(self):
        """Test to_dict serializes ElementType enum to its value."""
        sp = SemanticProperties(
            element_type=ElementType.DOOR,
            name="Main Door",
            height=2.1,
            width=0.9,
        )
        d = sp.to_dict()
        assert d["element_type"] == "door"
        assert d["name"] == "Main Door"
        assert d["height"] == 2.1
        assert d["width"] == 0.9

    def test_to_dict_with_string_type(self):
        """Test to_dict serializes string element_type as-is."""
        sp = SemanticProperties(element_type="custom", name="Custom Element")
        d = sp.to_dict()
        assert d["element_type"] == "custom"

    def test_to_dict_includes_all_fields(self):
        """Test that to_dict includes all field values."""
        sp = SemanticProperties(
            element_type=ElementType.WALL,
            name="Wall",
            description="Desc",
            material="steel",
            fire_rating="3HR",
            height=4.0,
            width=0.3,
            load_bearing=True,
            layer="S-WALL",
            revit_category="Structural Walls",
        )
        d = sp.to_dict()
        assert d["description"] == "Desc"
        assert d["material"] == "steel"
        assert d["fire_rating"] == "3HR"
        assert d["load_bearing"] is True
        assert d["layer"] == "S-WALL"
        assert d["revit_category"] == "Structural Walls"


# ═══════════════════════════════════════════════════════════════════════════
# Relationship Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRelationship:
    """Tests for the Relationship frozen dataclass."""

    def test_create_with_defaults(self):
        """Test creating a Relationship with default values."""
        r = Relationship()
        assert r.from_element_id == ""
        assert r.to_element_id == ""
        assert r.relationship_type == ""
        assert r.is_parametric is False
        assert r.metadata is None
        assert r.connection_id is None

    def test_create_with_all_fields(self):
        """Test creating a Relationship with all fields."""
        r = Relationship(
            from_element_id="elem-001",
            to_element_id="elem-002",
            relationship_type="adjacent",
            is_parametric=True,
            metadata={"distance": 0.5},
            connection_id="conn-001",
        )
        assert r.from_element_id == "elem-001"
        assert r.to_element_id == "elem-002"
        assert r.relationship_type == "adjacent"
        assert r.is_parametric is True
        assert r.metadata == {"distance": 0.5}
        assert r.connection_id == "conn-001"

    def test_frozen_immutability(self):
        """Test that Relationship is frozen (immutable)."""
        r = Relationship(from_element_id="a", to_element_id="b")
        with pytest.raises(AttributeError):
            r.relationship_type = "modified"  # type: ignore[misc]

    def test_to_dict(self):
        """Test to_dict serialization includes all fields including connection_id."""
        r = Relationship(
            from_element_id="elem-001",
            to_element_id="elem-002",
            relationship_type="contains",
            is_parametric=False,
            metadata={"key": "value"},
            connection_id="conn-abc",
        )
        d = r.to_dict()
        assert d["from_element_id"] == "elem-001"
        assert d["to_element_id"] == "elem-002"
        assert d["relationship_type"] == "contains"
        assert d["is_parametric"] is False
        assert d["metadata"] == {"key": "value"}
        assert d["connection_id"] == "conn-abc"

    def test_to_dict_includes_connection_id(self):
        """V83 FIX: connection_id was missing from to_dict — verify it's present."""
        r = Relationship(connection_id="conn-xyz")
        d = r.to_dict()
        assert "connection_id" in d
        assert d["connection_id"] == "conn-xyz"


# ═══════════════════════════════════════════════════════════════════════════
# Conflict Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestConflict:
    """Tests for the Conflict frozen dataclass."""

    def test_create_with_defaults(self):
        """Test creating a Conflict with default values."""
        c = Conflict()
        assert c.conflict_id == ""
        assert c.element_id == ""
        assert c.conflict_type == ConflictType.GEOMETRY_MISMATCH
        assert c.source_a is None
        assert c.source_b is None
        assert c.change_a is None
        assert c.change_b is None
        assert c.resolution is None
        assert c.resolved is False
        assert c.timestamp is None

    def test_create_with_all_fields(self):
        """Test creating a Conflict with all fields."""
        now = datetime.now(timezone.utc)
        c = Conflict(
            conflict_id="conflict-001",
            element_id="elem-001",
            conflict_type=ConflictType.PROPERTY_CONFLICT,
            source_a="autocad",
            source_b="revit",
            change_a={"x": 1.0},
            change_b={"x": 2.0},
            resolution={"strategy": "SEMANTIC_MERGE"},
            resolved=True,
            timestamp=now,
        )
        assert c.conflict_id == "conflict-001"
        assert c.element_id == "elem-001"
        assert c.conflict_type == ConflictType.PROPERTY_CONFLICT
        assert c.source_a == "autocad"
        assert c.source_b == "revit"
        assert c.resolved is True
        assert c.timestamp == now

    def test_frozen_immutability(self):
        """Test that Conflict is frozen (immutable)."""
        c = Conflict(conflict_id="test")
        with pytest.raises(AttributeError):
            c.resolved = True  # type: ignore[misc]

    def test_conflict_type_enum_values(self):
        """Test all ConflictType enum values are accessible."""
        assert ConflictType.GEOMETRY_MISMATCH.value == "geometry_mismatch"
        assert ConflictType.PROPERTY_CONFLICT.value == "property_conflict"
        assert ConflictType.DELETION_CONFLICT.value == "deletion_conflict"
        assert ConflictType.TIMING_CONFLICT.value == "timing_conflict"


# ═══════════════════════════════════════════════════════════════════════════
# UniversalElement Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestUniversalElement:
    """Tests for the UniversalElement frozen dataclass."""

    def test_create_with_mandatory_id(self):
        """Test creating a UniversalElement with mandatory element_id."""
        elem = UniversalElement(element_id="test-001")
        assert elem.element_id == "test-001"

    def test_reject_empty_element_id(self):
        """Test that empty element_id raises ValueError (V83 fix)."""
        with pytest.raises(ValueError, match="MANDATORY"):
            UniversalElement(element_id="")

    def test_reject_missing_element_id(self):
        """Test that missing element_id (defaults to '') raises ValueError."""
        with pytest.raises(ValueError, match="MANDATORY"):
            UniversalElement()

    def test_create_with_properties(self):
        """Test creating an element with SemanticProperties."""
        props = SemanticProperties(element_type=ElementType.WALL, name="Test Wall")
        elem = UniversalElement(element_id="wall-001", properties=props)
        assert elem.properties is not None
        assert elem.properties.name == "Test Wall"

    def test_create_with_geometry(self):
        """Test creating an element with Geometry."""
        geom = Geometry(
            points=(Point3D(x=0.0, y=0.0), Point3D(x=1.0, y=1.0)),
            polyline_closed=False,
        )
        elem = UniversalElement(element_id="geom-001", geometry=geom)
        assert elem.geometry is not None
        assert len(elem.geometry.points) == 2

    def test_create_with_relationships(self):
        """Test creating an element with Relationships."""
        rels = (
            Relationship(from_element_id="a", to_element_id="b", relationship_type="adjacent"),
            Relationship(from_element_id="a", to_element_id="c", relationship_type="contains"),
        )
        elem = UniversalElement(element_id="rel-001", relationships=rels)
        assert len(elem.relationships) == 2

    def test_default_values(self):
        """Test default field values for UniversalElement."""
        elem = UniversalElement(element_id="defaults-001")
        assert elem.properties is None
        assert elem.geometry is None
        assert elem.relationships == ()
        assert elem.source_file is None
        assert elem.last_modified_by is None
        assert elem.autocad_handle is None
        assert elem.revit_element_id is None
        assert elem.created_timestamp is None
        assert elem.last_modified_timestamp is None
        assert elem.version == 0
        assert elem.is_deleted is False
        assert elem.project_id is None

    def test_frozen_immutability(self):
        """Test that UniversalElement is frozen (immutable)."""
        elem = UniversalElement(element_id="frozen-001")
        with pytest.raises(AttributeError):
            elem.version = 5  # type: ignore[misc]

    def test_to_dict_minimal(self):
        """Test to_dict with minimal element (only element_id)."""
        elem = UniversalElement(element_id="min-001")
        d = elem.to_dict()
        assert d["element_id"] == "min-001"
        assert "properties" not in d  # None properties not included
        assert "geometry" not in d  # None geometry not included
        assert d["relationships"] == []

    def test_to_dict_with_properties(self):
        """Test to_dict includes serialized properties."""
        props = SemanticProperties(element_type=ElementType.DOOR, name="Door 1", height=2.1)
        elem = UniversalElement(element_id="prop-001", properties=props)
        d = elem.to_dict()
        assert "properties" in d
        assert d["properties"]["element_type"] == "door"
        assert d["properties"]["name"] == "Door 1"
        assert d["properties"]["height"] == 2.1

    def test_to_dict_with_geometry(self):
        """Test to_dict includes serialized geometry."""
        geom = Geometry(
            points=(Point3D(x=1.0, y=2.0, z=3.0),),
            polyline_closed=False,
        )
        elem = UniversalElement(element_id="geom-001", geometry=geom)
        d = elem.to_dict()
        assert "geometry" in d
        assert d["geometry"]["points"][0] == {"x": 1.0, "y": 2.0, "z": 3.0}
        assert d["geometry"]["polyline_closed"] is False

    def test_to_dict_with_relationships(self):
        """Test to_dict includes serialized relationships."""
        rels = (
            Relationship(from_element_id="a", to_element_id="b", relationship_type="adj"),
        )
        elem = UniversalElement(element_id="rel-001", relationships=rels)
        d = elem.to_dict()
        assert len(d["relationships"]) == 1
        assert d["relationships"][0]["from_element_id"] == "a"

    def test_to_dict_with_timestamps(self):
        """Test to_dict serializes timestamps as ISO format strings."""
        now = datetime.now(timezone.utc)
        elem = UniversalElement(
            element_id="ts-001",
            created_timestamp=now,
            last_modified_timestamp=now,
        )
        d = elem.to_dict()
        assert d["created_timestamp"] == now.isoformat()
        assert d["last_modified_timestamp"] == now.isoformat()

    def test_to_dict_null_timestamps(self):
        """Test to_dict serializes None timestamps as null."""
        elem = UniversalElement(element_id="nts-001")
        d = elem.to_dict()
        assert d["created_timestamp"] is None
        assert d["last_modified_timestamp"] is None

    def test_to_dict_all_fields(self):
        """Test to_dict with all fields populated."""
        now = datetime.now(timezone.utc)
        elem = UniversalElement(
            element_id="full-001",
            properties=SemanticProperties(element_type=ElementType.WALL, name="Full"),
            geometry=Geometry(points=(Point3D(x=0.0, y=0.0),)),
            relationships=(Relationship(from_element_id="full-001", to_element_id="other"),),
            source_file="test.dwg",
            last_modified_by="autocad",
            autocad_handle="H1",
            revit_element_id=42,
            created_timestamp=now,
            last_modified_timestamp=now,
            version=3,
            is_deleted=False,
            project_id="proj-x",
        )
        d = elem.to_dict()
        assert d["element_id"] == "full-001"
        assert d["source_file"] == "test.dwg"
        assert d["autocad_handle"] == "H1"
        assert d["revit_element_id"] == 42
        assert d["version"] == 3
        assert d["project_id"] == "proj-x"


# ═══════════════════════════════════════════════════════════════════════════
# Enumeration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestElementType:
    """Tests for the ElementType enumeration."""

    def test_all_values(self):
        """Test all ElementType enum values exist."""
        expected = {"wall", "door", "window", "room", "equipment", "mechanical", "electrical", "unknown"}
        actual = {e.value for e in ElementType}
        assert actual == expected

    def test_string_enum(self):
        """Test that ElementType is a string enum."""
        assert isinstance(ElementType.WALL, str)
        assert ElementType.WALL == "wall"

    def test_from_value(self):
        """Test creating ElementType from its string value."""
        assert ElementType("door") == ElementType.DOOR
        assert ElementType("window") == ElementType.WINDOW


class TestChangeSource:
    """Tests for the ChangeSource enumeration."""

    def test_all_values(self):
        """Test all ChangeSource enum values exist."""
        expected = {"autocad", "revit", "manual", "system"}
        actual = {e.value for e in ChangeSource}
        assert actual == expected

    def test_string_enum(self):
        """Test that ChangeSource is a string enum."""
        assert isinstance(ChangeSource.REVIT, str)
        assert ChangeSource.REVIT == "revit"


class TestConflictType:
    """Tests for the ConflictType enumeration."""

    def test_all_values(self):
        """Test all ConflictType enum values exist."""
        expected = {"geometry_mismatch", "property_conflict", "deletion_conflict", "timing_conflict"}
        actual = {e.value for e in ConflictType}
        assert actual == expected

    def test_string_enum(self):
        """Test that ConflictType is a string enum."""
        assert isinstance(ConflictType.GEOMETRY_MISMATCH, str)

    def test_from_value(self):
        """Test creating ConflictType from its string value."""
        assert ConflictType("property_conflict") == ConflictType.PROPERTY_CONFLICT


# ═══════════════════════════════════════════════════════════════════════════
# Module Re-export Tests (core/__init__.py)
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleReExports:
    """Tests that core/__init__.py correctly re-exports all public symbols."""

    def test_import_point3d(self):
        """Test that Point3D is importable from core."""
        from core import Point3D as P
        assert P is Point3D

    def test_import_geometry(self):
        """Test that Geometry is importable from core."""
        from core import Geometry as G
        assert G is Geometry

    def test_import_universal_element(self):
        """Test that UniversalElement is importable from core."""
        from core import UniversalElement as UE
        assert UE is UniversalElement

    def test_import_semantic_properties(self):
        """Test that SemanticProperties is importable from core."""
        from core import SemanticProperties as SP
        assert SP is SemanticProperties

    def test_import_relationship(self):
        """Test that Relationship is importable from core."""
        from core import Relationship as R
        assert R is Relationship

    def test_import_conflict(self):
        """Test that Conflict is importable from core."""
        from core import Conflict as C
        assert C is Conflict

    def test_import_element_type(self):
        """Test that ElementType is importable from core."""
        from core import ElementType as ET
        assert ET is ElementType

    def test_import_change_source(self):
        """Test that ChangeSource is importable from core."""
        from core import ChangeSource as CS
        assert CS is ChangeSource

    def test_import_conflict_type(self):
        """Test that ConflictType is importable from core."""
        from core import ConflictType as CT
        assert CT is ConflictType

    def test_import_universal_data_model(self):
        """Test that UniversalDataModel is importable from core."""
        from core import UniversalDataModel as UDM
        from core.database import UniversalDataModel
        assert UDM is UniversalDataModel
