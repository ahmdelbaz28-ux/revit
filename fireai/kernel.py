"""FireAI Kernel — Standalone Engineering Engine
=============================================
This is the decoupled core of the FireAI platform.
It can be run as a standalone library without FastAPI or a UI.
"""

from fireai.core.spatial_engine.density_optimizer import GenerativeOptimizer, Room
from fireai.core.analysis_pipeline import AnalysisPipeline
from fireai.core.digital_twin import DigitalTwin
from fireai.core.event_bus import EventBus, Events


class FireAIKernel:
    """
    Main entry point for the decoupled FireAI engineering engine.
    """

    def __init__(self, building_id: str):
        self.building_id = building_id
        self.bus = EventBus.instance()
        self.twin = DigitalTwin(building_id=building_id)
        self.pipeline = AnalysisPipeline()

    def run_generative_design(self, room_data: dict):
        """Run generative design variants for a room."""
        room = Room(
            name=room_data["name"],
            width=room_data["width"],
            length=room_data["length"]
        )
        gen = GenerativeOptimizer(room)
        return gen.generate_variants()

    def process_building(self, rooms: list):
        """Process an entire building for NFPA compliance."""
        results = self.pipeline.analyze_building(rooms)
        # Sync to twin
        for res in results:
            if res.success:
                # Digital Twin integration logic
                pass
        return results
