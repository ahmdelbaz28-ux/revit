"""tests/test_design_agent.py — Design Agent Tests (all require human approval)"""

import sys
from pathlib import Path
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.services.design_agent import DesignAgent, DesignProposal, DetectorProposal


@pytest.fixture
def agent():
    return DesignAgent()


class TestDesignAgentPropose:
    def test_propose_smoke_detector(self, agent):
        proposal = agent.propose("R1", "Office", 50.0, 10.0, 5.0, "smoke")
        assert proposal.room_id == "R1"
        assert proposal.total_detectors >= 1
        assert proposal.approved is False  # NEVER auto-approved

    def test_propose_heat_detector(self, agent):
        proposal = agent.propose("R2", "Kitchen", 30.0, 6.0, 5.0, "heat")
        assert proposal.total_detectors >= 1
        assert proposal.approved is False

    def test_propose_zero_area(self, agent):
        proposal = agent.propose("R3", "Empty", 0.0)
        assert proposal.total_detectors == 0

    def test_propose_has_disclaimer(self, agent):
        proposal = agent.propose("R4", "Office", 50.0, 10.0, 5.0)
        assert "ADVISORY ONLY" in proposal.disclaimer

    def test_propose_has_correlation_id(self, agent):
        proposal = agent.propose("R5", "Office", 50.0)
        assert proposal.correlation_id.startswith("design-")

    def test_propose_coverage_estimate(self, agent):
        proposal = agent.propose("R6", "Hall", 100.0, 20.0, 5.0)
        assert 0 <= proposal.estimated_coverage_pct <= 100


class TestDesignAgentApprove:
    def test_approve_with_human(self, agent):
        proposal = agent.propose("R1", "Office", 50.0, 10.0, 5.0)
        assert proposal.approved is False
        approved = agent.approve(proposal, "Eng. Ahmed")
        assert approved.approved is True
        assert approved.approved_by == "Eng. Ahmed"
        assert approved.approved_at

    def test_approve_requires_name(self, agent):
        proposal = agent.propose("R1", "Office", 50.0)
        with pytest.raises(ValueError, match="auto-approval"):
            agent.approve(proposal, "")

    def test_reject_proposal(self, agent):
        proposal = agent.propose("R1", "Office", 50.0)
        rejected = agent.reject(proposal, "Insufficient coverage")
        assert rejected.approved is False
        assert "REJECTED" in rejected.approved_by


class TestDesignAgentSafety:
    def test_never_auto_approves(self, agent):
        """CRITICAL: Agent must NEVER auto-approve."""
        proposal = agent.propose("R1", "Office", 500.0, 30.0, 20.0)
        assert proposal.approved is False

    def test_coverage_radii_correct(self, agent):
        """NFPA 72 coverage radii must be 0.7 × nominal spacing."""
        assert abs(agent.SMOKE_RADIUS - 6.37) < 0.1  # 0.7 × 9.1m
        assert abs(agent.HEAT_RADIUS - 10.64) < 0.1  # 0.7 × 15.2m
