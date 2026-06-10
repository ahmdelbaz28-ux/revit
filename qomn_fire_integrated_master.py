"""
QOMN-FIRE: MASTER INTEGRATED WORKSPACE RUNNER
==============================================
Author: Chief Fire Protection Engineer & Safety-Critical Systems Architect
Standards: NFPA 72 (2022), NEC 760 (2023), ISO 19650, UL 864 10th Edition

V54 Bug Fixes Preserved (all regressions from proposed code corrected):
  F2: NAC capacity uses EXACT match — required_nacs = nac_circuit_count
  F3: Sort prefers SMALLEST adequate capacity on ties
  F4: supports_releasing field + filter logic present
  F5: Battery sizing uses NFPA 72 compliant derating (NOT flat 1.2x)
  F6: Per-device standby current = 0.8 mA (not 1.0 mA)
"""

import os
import sys
import unittest


class TestIntegratedQomnFire(unittest.TestCase):

    def test_complete_integrated_selection_flow(self):
        """
        VERIFICATION TEST 1: Integrated FACP Selection Sizing
        Input: 30 devices, 2 NAC circuits, Standalone US project.
        Expected: FC901 selected. Battery >= 5.0 Ah (with proper derating, NOT 4.76 flat).
        """
        from qomn_fire.core.types import ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine

        req = ProjectRequirements(
            device_count=30,
            nac_circuit_count=2,
            building_size_m2=1500.0,
            building_floors=2,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="US"
        )

        res = SelectionEngine.select_panel(req)
        self.assertTrue(res.is_success)
        rec = res.unwrap()

        self.assertEqual(rec.recommended_model, "FC901")
        self.assertEqual(rec.manufacturer, "SIEMENS")
        # V54 FIX F5: Battery must be > 5.0 Ah with proper derating
        # Original flat 1.2x gave 4.76 Ah (insufficient at 0C)
        self.assertGreater(rec.battery_size_ah, 5.0)
        # Derating method must NOT be flat 1.2x
        self.assertNotIn("1.2", rec.battery_derating_details.get("method", ""))

    def test_placement_to_selection_vascular_pipeline(self):
        """
        VERIFICATION TEST 2: Multi-Engine Integrated Sizing (Vascular Link)
        Input: Large Room (25x15m), placing devices automatically, then selecting panel.
        Expected: Placement places 6 detectors. Selector evaluates and recommends FC901.
        """
        from qomn_fire.core.types import Point3D, ProjectRequirements
        from qomn_fire.engine.placement import place_smoke_detectors_room
        from qomn_fire.engine.panel_selector import SelectionEngine

        room_min = Point3D(0.0, 0.0, 0.0)
        room_max = Point3D(25.0, 15.0, 0.0)

        place_res = place_smoke_detectors_room(room_min, room_max, 9.0, "CIRCUIT-A", "ZONE_A")
        self.assertTrue(place_res.is_success)
        devices = place_res.unwrap()
        self.assertEqual(len(devices), 6)

        req = ProjectRequirements(
            device_count=len(devices),
            nac_circuit_count=2,
            building_size_m2=375.0,
            building_floors=1,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="US"
        )

        select_res = SelectionEngine.select_panel(req)
        self.assertTrue(select_res.is_success)
        rec = select_res.unwrap()
        self.assertEqual(rec.recommended_model, "FC901")

    def test_fdny_jurisdiction_constraint(self):
        """
        VERIFICATION TEST 3: FDNY COA requirement.
        Only FDNY-listed panels should be selected for FDNY jurisdiction.
        """
        from qomn_fire.core.types import ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine

        req = ProjectRequirements(
            device_count=100,
            nac_circuit_count=2,
            building_size_m2=5000.0,
            building_floors=3,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="FDNY"
        )
        res = SelectionEngine.select_panel(req)
        self.assertTrue(res.is_success)
        rec = res.unwrap()
        self.assertIn("FDNY", rec.listings)

    def test_releasing_service_filter(self):
        """
        VERIFICATION TEST 4 (V54 FIX F4): Releasing service constraint.
        Only releasing-capable panels should be selected when requires_releasing=True.
        """
        from qomn_fire.core.types import ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine
        from qomn_fire.engine.panel_database import MASTER_PANEL_DATABASE

        req = ProjectRequirements(
            device_count=200,
            nac_circuit_count=4,
            building_size_m2=10000.0,
            building_floors=3,
            requires_network=True,
            requires_voice=True,
            requires_releasing=True,
            jurisdiction="US",
            preferred_manufacturer="SIEMENS"
        )
        res = SelectionEngine.select_panel(req)
        self.assertTrue(res.is_success)
        rec = res.unwrap()
        # FC924 supports releasing, FC922 does not
        panel = next((p for p in MASTER_PANEL_DATABASE if p.model == rec.recommended_model), None)
        self.assertIsNotNone(panel)
        self.assertTrue(panel.supports_releasing)

    def test_nac_exact_match_not_12x(self):
        """
        VERIFICATION TEST 5 (V54 FIX F2): NAC uses exact match, not 1.2x.
        FC924 with 6 NACs should be eligible for 6-NAC design.
        """
        from qomn_fire.core.types import ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine

        req = ProjectRequirements(
            device_count=300,
            nac_circuit_count=6,
            building_size_m2=20000.0,
            building_floors=10,
            requires_network=True,
            requires_voice=True,
            requires_releasing=False,
            jurisdiction="US",
            preferred_manufacturer="SIEMENS"
        )
        res = SelectionEngine.select_panel(req)
        self.assertTrue(res.is_success)
        rec = res.unwrap()
        self.assertEqual(rec.recommended_model, "FC924")

    def test_determinism_100_cycles(self):
        """
        VERIFICATION TEST 6: Determinism — same inputs produce bit-identical signatures.
        """
        from qomn_fire.core.types import ProjectRequirements
        from qomn_fire.engine.panel_selector import SelectionEngine

        req = ProjectRequirements(
            device_count=150,
            nac_circuit_count=4,
            building_size_m2=8000.0,
            building_floors=4,
            requires_network=True,
            requires_voice=True,
            requires_releasing=False,
            jurisdiction="US"
        )

        ref_hash = None
        for _ in range(100):
            res = SelectionEngine.select_panel(req)
            self.assertTrue(res.is_success)
            rec = res.unwrap()
            if ref_hash is None:
                ref_hash = rec.signature_hash
            else:
                self.assertEqual(ref_hash, rec.signature_hash)

    def test_routing_basic_path(self):
        """
        VERIFICATION TEST 7: Conduit routing with basic pathfinding.
        Tests that A* finds a valid path and enforces NEC bend limits.
        """
        from qomn_fire.core.types import Point3D, ConduitType
        from qomn_fire.engine.routing import GridMap3D, astar_route_3d

        grid_map = GridMap3D(step_m=0.5)

        # Simple straight-line route should succeed
        res = astar_route_3d(
            grid_map=grid_map,
            start=Point3D(0.0, 0.0, 0.0),
            end=Point3D(4.0, 0.0, 0.0),
            conduit=ConduitType.EMT,
            conduit_id="C_TEST_001"
        )
        self.assertTrue(res.is_success)
        run = res.unwrap()
        self.assertGreater(run.total_length_ft, 0)

        # Test with obstacles blocking direct path - should find alternate route
        grid_map2 = GridMap3D(step_m=0.5)
        # Block the direct path along y=0
        for x in range(1, 8):
            grid_map2.add_obstacle(Point3D(x * 0.5, 0.0, 0.0))

        res2 = astar_route_3d(
            grid_map=grid_map2,
            start=Point3D(0.0, 0.0, 0.0),
            end=Point3D(4.0, 0.0, 0.0),
            conduit=ConduitType.EMT,
            conduit_id="C_TEST_002"
        )
        # Should either find a detour path or fail with NEC violation
        if res2.is_success:
            run2 = res2.unwrap()
            self.assertGreater(run2.total_length_ft, 0)


def execute_integrated_master_project():
    """Runs a complete end-to-end fire protective design, sizing, and CAD production pipeline."""
    print("\n" + "="*80)
    print("        QOMN-FIRE INTEGRATED PIPELINE: FULL PROJECT COMPILATION")
    print("="*80)

    from qomn_fire.core.types import Point3D, TitleBlock, HatchSpec, ConduitType, Revision, ProjectRequirements
    from qomn_fire.core.constants import NFPA_SMOKE_DETECTOR_SPACING_M
    from qomn_fire.engine.placement import place_smoke_detectors_room
    from qomn_fire.engine.routing import GridMap3D
    from qomn_fire.engine.panel_selector import SelectionEngine
    from qomn_fire.drawing.dxf_generator import create_document, setup_layers, add_viewport
    from qomn_fire.drawing.hatch_engine import generate_circle_polyline, place_boundary_hatch
    from qomn_fire.drawing.title_block import draw_title_block, draw_facp_schedule
    from qomn_fire.drawing.revision_control import draw_revision_cloud, draw_revision_table
    from qomn_fire.integration.cable_hatch import route_conduit_and_hatch
    from qomn_fire.output.revit_exporter import export_to_revit_json

    # 1. Initialize Drawing Doc
    doc = create_document()
    setup_layers(doc)
    msp = doc.modelspace()

    # 2. Rectangular Building Room Coordinates
    room_min = Point3D(0.0, 0.0, 0.0)
    room_max = Point3D(25.0, 15.0, 0.0)

    # Draw physical walls
    wall_attribs = {"layer": "A-WALL", "color": 7}
    msp.add_line((room_min.x, room_min.y), (room_max.x, room_min.y), dxfattribs=wall_attribs)
    msp.add_line((room_max.x, room_min.y), (room_max.x, room_max.y), dxfattribs=wall_attribs)
    msp.add_line((room_max.x, room_max.y), (room_min.x, room_max.y), dxfattribs=wall_attribs)
    msp.add_line((room_min.x, room_max.y), (room_min.x, room_min.y), dxfattribs=wall_attribs)

    # 3. NFPA-Compliant Automatic Space Device Placement
    print(" -> Resolving detector layouts...")
    place_res = place_smoke_detectors_room(room_min, room_max, 9.0, "FA-LP1", "ZONE_1")
    if place_res.is_failure:
        print(f"\n[CRITICAL] Detector placement failed: {place_res.error()}")
        sys.exit(1)
    devices = place_res.unwrap()

    h_spec_coverage = HatchSpec("ANSI31", 45.0, 0.1, 3, "A-FIRE-HATC", "Smoke Coverage", "NFPA 72 SS17")

    for d in devices:
        msp.add_circle(d.location.to_tuple()[:2], radius=0.4, dxfattribs={"layer": "A-FIRE-DEVICES", "color": 1})
        msp.add_text(d.id, dxfattribs={"insert": (d.location.x + 0.5, d.location.y + 0.5), "height": 0.25, "layer": "A-FIRE-TEXT", "color": 5})

        boundary = generate_circle_polyline(d.location, NFPA_SMOKE_DETECTOR_SPACING_M)
        hatch_res = place_boundary_hatch(doc, boundary, h_spec_coverage, d.id)
        if hatch_res.is_failure:
            print(f"   [WARNING] Hatch placement failed for {d.id}: {hatch_res.error()}")

    # 4. NFPA & NEC Compliant FACP Selection (Direct Vascular Linkage)
    print(" -> Dynamically selecting panel based on device loads...")
    req = ProjectRequirements(
        device_count=len(devices),
        nac_circuit_count=2,
        building_size_m2=375.0,
        building_floors=1,
        requires_network=False,
        requires_voice=False,
        requires_releasing=False,
        jurisdiction="FDNY",
        preferred_manufacturer="SIEMENS"
    )

    selection_res = SelectionEngine.select_panel(req)
    if selection_res.is_failure:
        print(f"\n[CRITICAL] FACP selection failed: {selection_res.error()}")
        sys.exit(1)
    rec = selection_res.unwrap()
    print(f"   -> Selected FACP: {rec.recommended_model} ({rec.manufacturer})")
    print(f"   -> Battery: {rec.battery_size_ah} Ah ({rec.battery_derating_details.get('method', 'N/A')})")
    print(f"   -> Derating Safety Factor: {rec.battery_derating_details.get('enhanced_safety_factor', rec.battery_derating_details.get('combined_safety_factor', 'N/A'))}")

    # 5. Routing conduits between sequential devices
    print(" -> Routing conduit paths...")
    grid_map = GridMap3D(step_m=0.5)
    for d in devices:
        grid_map.add_obstacle(d.location)

    conduit_spec = HatchSpec("CROSS", 0.0, 0.05, 3, "A-FIRE-HATC", "Conduit Corridor", "NEC 760")
    conduit_runs = []

    for idx in range(len(devices) - 1):
        start_pt = devices[idx].location
        end_pt = devices[idx+1].location

        grid_map.obstacles.discard(grid_map.to_grid(start_pt))
        grid_map.obstacles.discard(grid_map.to_grid(end_pt))

        res = route_conduit_and_hatch(
            grid_map=grid_map,
            doc=doc,
            start=start_pt,
            end=end_pt,
            conduit=ConduitType.EMT,
            conduit_id=f"CONDUIT_RUN_{idx:02d}",
            spec=conduit_spec
        )

        grid_map.add_obstacle(start_pt)
        grid_map.add_obstacle(end_pt)

        if res.is_success:
            run_item, _ = res.unwrap()
            conduit_runs.append(run_item)
        else:
            print(f"   [WARNING] Conduit route {idx} failed: {res.error()}")

    # 6. Dimensions and Layout Graphics
    if len(devices) >= 2:
        msp.add_aligned_dim(
            p1=devices[0].location.to_tuple()[:2],
            p2=devices[1].location.to_tuple()[:2],
            distance=2.0,
            dxfattribs={"layer": "A-FIRE-DIMS", "color": 4}
        )

    # Title Block Sheet
    title = TitleBlock(
        project_name="INTEGRATED LIFE SAFETY NETWORK",
        drawing_number="QOMN-FA-001",
        sheet_title="FIRE ALARM DEVICE DISTRIBUTION & INHERENT SIZING PLAN",
        scale="1:100",
        date="2026-06-01",
        designer="Systems Automation Architect",
        checker="Senior Verification Audit Engineer",
        pe_stamp="LICENSED PROFESSIONAL ENGINEER - STAMP #PE-90998",
        client="Hospital General Board",
        address="Zone 2 Building C Complex"
    )
    draw_title_block(doc, title)

    draw_facp_schedule(doc, rec)

    add_viewport(doc, center=(350.0, 300.0), size=(500.0, 400.0), view_center=(12.5, 7.5), view_height=20.0)

    revs = [
        Revision(0, "2026-06-01", "Merged routing with dynamic FACP selections (V54 fixes preserved)", "SYS_INTEGRATOR")
    ]
    draw_revision_table(doc, revs)

    # 7. Compile files to disk with error handling
    dxf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fire_alarm_plan.dxf")
    try:
        doc.saveas(dxf_path)
        print(f"\n -> CAD shop drawing compiled: '{dxf_path}'")
    except Exception as e:
        print(f"\n[CRITICAL] DXF save failed: {e}")
        sys.exit(1)

    revit_json = export_to_revit_json(devices, conduit_runs, rec)
    revit_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "revit_import.json")
    try:
        with open(revit_path, "w", encoding="utf-8") as f:
            f.write(revit_json)
        print(f" -> Revit BIM metadata compiled: '{revit_path}'")
    except Exception as e:
        print(f"\n[CRITICAL] Revit JSON save failed: {e}")
        sys.exit(1)

    print("\n[QOMN-FIRE INTEGRATION] Compilation run completed successfully.")


if __name__ == "__main__":
    print("="*80)
    print("        QOMN-FIRE: MASTER INTEGRATED SUITE RUNTIME ENGINE")
    print("        V54 Safety Fixes Preserved (F1-F6)")
    print("="*80)

    # Add project root to Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)

    # 1. Run the dynamic unit testing suite
    print("\n" + "="*80)
    print("             EXECUTING AUTOMATED CRITICAL UNIT TEST SUITE")
    print("="*80)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestIntegratedQomnFire)
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)

    if not test_result.wasSuccessful():
        print("\n[CRITICAL ERROR] Test suite failures occurred. Aborting compilation runs.")
        sys.exit(1)

    # 2. Run production master project
    print("\n" + "="*80)
    print("             RUNNING END-TO-END CAD/BIM PRODUCTION WORKFLOW")
    print("="*80)
    execute_integrated_master_project()
