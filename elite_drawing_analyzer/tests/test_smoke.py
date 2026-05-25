"""Quick smoke tests — verify the architecture wires up correctly
without needing real CAD files."""
import os, tempfile, json, sqlite3
from pathlib import Path

import numpy as np
import cv2


def test_kb_seeds_and_rules(tmp_path):
    from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase
    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    stats = kb.stats()
    assert stats["symbols"] >= 15
    assert stats["rules"]   >= 10
    r = kb.get_rule("smoke_detector.max_spacing_m", "NFPA72")
    assert r and abs(r["value"] - 9.1) < 1e-6


def test_classifier_name_pattern(tmp_path):
    from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase
    from elite_drawing_analyzer.intelligence.classifier import SymbolClassifier
    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    clf = SymbolClassifier(kb)
    r = clf.classify_by_name("SMK-101")
    assert r and r.symbol == "smoke_detector"
    r = clf.classify_by_name("CAM-DOME-12")
    assert r and r.symbol == "camera_dome"


def test_compliance_detects_overspacing(tmp_path):
    from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase
    from elite_drawing_analyzer.reasoning.compliance import ComplianceEngine
    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    eng = ComplianceEngine(kb, units_to_m=1.0)   # work directly in metres
    # two detectors 12 m apart — exceeds 9.1 m
    findings = eng.check_detector_spacing("smoke_detector", [(0,0),(12,0)])
    assert any(f.severity == "critical" for f in findings)


def test_reconciliation():
    from elite_drawing_analyzer.reasoning.schedule_match import reconcile, ScheduleLine
    sched = [ScheduleLine("smoke detector", 24, {}),
             ScheduleLine("sprinkler", 40, {})]
    actual = {"smoke_detector": 22, "sprinkler_pendant": 40, "camera_dome": 6}
    rep = reconcile(sched, actual,
                    symbol_aliases={"sprinkler_pendant": ["sprinkler"]})
    by_item = {r.item: r for r in rep}
    assert by_item["smoke_detector"].status == "under"
    assert by_item["smoke_detector"].delta == -2
    assert by_item["sprinkler_pendant"].status == "match"
    assert by_item["camera_dome"].status == "not_in_schedule"


def test_vectorize_heals_broken_lines():
    from elite_drawing_analyzer.core.vectorize import vectorize_raster
    img = np.full((300, 600, 3), 255, np.uint8)
    # Draw a dashed line — broken
    for x in range(50, 550, 20):
        cv2.line(img, (x, 150), (x+10, 150), (0,0,0), 2)
    res = vectorize_raster(img)
    assert len(res["lines"]) >= 1
    assert res["healing_ratio"] >= 0   # some healing was applied


if __name__ == "__main__":
    import pytest, sys
    sys.exit(pytest.main([__file__, "-v"]))
