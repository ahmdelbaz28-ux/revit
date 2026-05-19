import unittest
from core.gkil.proof_engine import ProofStatus
from core.gkil.cad_data_model import GeoGraph, GeoMorphism, ObstacleType, Point3D
from core.compliance_engine.reg_lattice import RegLattice
from core.compliance_engine.gel_compiler import GovernanceCompiler

class TestRegulatoryPenetration(unittest.TestCase):

    def setUp(self):
        """
        Baseline Setup: Initialize frozen engine, a 10x10 zone, and one detector.
        """
        self.geo_graph = GeoGraph()
        self.reg_lattice = RegLattice(edition="NFPA_72_2022")
        self.compiler = GovernanceCompiler(self.geo_graph, self.reg_lattice)

        # Build ground truth
        self.zone_id = self.geo_graph.create_zone(width=10.0, length=10.0, name="Zone_101")
        self.detector_id = self.geo_graph.insert_node(
            node_type="Detector", 
            coordinates=Point3D(5.0, 5.0, 3.0), 
            host_zone=self.zone_id
        )

        # Generate baseline proof
        self.baseline_proof = self.compiler.evaluate_project()
        self.baseline_token = self.baseline_proof.master_proof_token

    def test_tamper_proof_delta_d_violation(self):
        """
        Penetration Test: Inject a SolidWall to break coverage and verify system response.
        """
        print("\n[TEST] Starting Regulatory Penetration Test...")
        print(f"[INFO] Baseline Token: {self.baseline_token}")
        
        # Assert baseline is valid
        self.assertEqual(self.baseline_proof.status, ProofStatus.VALID)

        # --- Inject Delta D (Obstacle) ---
        print("[ACTION] Injecting SolidWall separating the zone...")
        morphism = GeoMorphism.InsertObstacle(
            obstacle_type=ObstacleType.SOLID_WALL,
            start_point=Point3D(5.0, 0.0, 0.0),
            end_point=Point3D(5.0, 10.0, 0.0),
            zone=self.zone_id
        )
        
        # Apply change via incremental compilation
        new_proof_dag = self.compiler.apply_morphism(morphism)

        # --- Automated Assertions ---
        
        # 1. Verify project status shifts to FAILED
        self.assertEqual(new_proof_dag.status, ProofStatus.FAILED, "System failed to detect the coverage violation!")
        
        # 2. Verify semantic isolation and hash mutation
        leaf_proof = new_proof_dag.get_leaf_proof(self.zone_id)
        self.assertNotEqual(
            leaf_proof.geo_hash, 
            self.baseline_proof.get_leaf_proof(self.zone_id).geo_hash,
            "GeoHash did not change after architectural mutation!"
        )

        # 3. Verify physical reasoning (Line of Sight)
        self.assertIn(
            "Line of Sight Blocked", 
            leaf_proof.violation_details.reason,
            "Violation reason does not accurately reflect the physical constraint."
        )

        # 4. Verify Master Token regeneration (Cryptographic Seal)
        self.assertNotEqual(
            new_proof_dag.master_proof_token, 
            self.baseline_token,
            "MasterProofToken remained identical! Cryptographic seal broken."
        )

        print(f"[SUCCESS] Violation caught. New Master Token generated: {new_proof_dag.master_proof_token}")
        print("[SUCCESS] Penetration Test Passed. Governance Layer is secure.")

if __name__ == '__main__':
    unittest.main()