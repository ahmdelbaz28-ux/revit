"""More tests covering v0.2 features."""
import json, tempfile
from pathlib import Path

import numpy as np
import cv2


def test_active_learning_round_trip(tmp_path):
    from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase
    from elite_drawing_analyzer.intelligence.active_learning import (
        review_pending, submit_feedback, metrics)

    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    # Insert a fake low-confidence decision
    did = kb.record_decision("sha_xyz", 0, (10,10,42,42), "unknown", 0.2)
    pending = review_pending(kb)
    assert any(r["id"] == did for r in pending)

    crop = tmp_path / "crop.png"
    cv2.imwrite(str(crop), np.full((40,40,3), 200, np.uint8))
    res = submit_feedback(kb, did, is_correct=False,
                          correction="smoke_detector", crop_image_path=str(crop))
    assert res["final_label"] == "smoke_detector"
    m = metrics(kb)
    assert m["total_judged"] == 1
    assert m["corrected"]    == 1
    # And the example should now be in the KB
    assert kb.conn.execute("SELECT COUNT(*) FROM symbol_examples").fetchone()[0] == 1


def test_overlay_renders_blank(tmp_path):
    from elite_drawing_analyzer.pipeline import Report
    from elite_drawing_analyzer.reporting.overlay import render_overlay

    rep = Report(file="dummy.pdf", file_type="pdf", file_sha="x", summary={"pages":1},
                 elements=[{"page":0,"bbox":(10,10,50,50),
                            "classification":{"symbol":"smoke_detector","confidence":0.9,
                                              "reasoning":"test"}}],
                 counts={"smoke_detector":1}, findings=[], reconciliation=[],
                 ocr_texts=[], warnings=[], elapsed_seconds=0.1)
    paths = render_overlay(rep, str(tmp_path))
    assert paths and Path(paths[0]).exists()


def test_html_report_self_contained(tmp_path):
    from elite_drawing_analyzer.pipeline import Report
    from elite_drawing_analyzer.reporting.html_report import generate_report_html

    rep = Report(file="d.pdf", file_type="pdf", file_sha="abc", summary={"pages":1},
                 elements=[], counts={"smoke_detector":3},
                 findings=[{"severity":"critical","code":"NFPA72",
                            "rule":"smoke_detector.max_spacing_m",
                            "message":"Too far apart","citation":"§17.6",
                            "recommendation":"add one"}],
                 reconciliation=[{"item":"smoke_detector","scheduled_qty":4,
                                  "actual_qty":3,"delta":-1,"status":"under","note":""}],
                 ocr_texts=[], warnings=["watch this"], elapsed_seconds=0.2)
    out = tmp_path / "r.html"
    generate_report_html(rep, out_path=str(out))
    txt = out.read_text()
    assert "Elite Drawing Analyzer" in txt
    assert "NFPA72" in txt
    assert "Schedule reconciliation" in txt


def test_safety_gates(tmp_path):
    from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase
    from elite_drawing_analyzer.safety.fire import (
        gate_smoke_detection_coverage, run_all_gates)
    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    g = gate_smoke_detection_coverage(kb, [(0,0),(8,0),(16,0)], units_to_m=1.0)
    # 16 m between far ones, but min-neighbour is 8 (OK). spacing rule = 9.1
    assert g.status == "pass"
    # Now make it fail
    g2 = gate_smoke_detection_coverage(kb, [(0,0),(15,0)], units_to_m=1.0)
    assert g2.status == "fail"


if __name__ == "__main__":
    import pytest, sys
    sys.exit(pytest.main([__file__, "-v"]))
