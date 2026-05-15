#!/usr/bin/env python3
"""
V&V ANALYSIS SCRIPT — Golden Dataset Runner
=============================================
يمرر كل PDF في مجلد عبر المسار الكامل:
PDF → InputPipeline → CoveragePipeline → CSV

الاستخدام:
    python scripts/run_vv_analysis.py /path/to/pdf/folder/ [--output results.csv]

Author: The Consultant Who Refused to Lie
"""

import sys
import os
import csv
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional

# تأكد من أن المجلد الجذر في PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.input_pipeline import InputPipeline, PipelineStatus
from src.core.coverage_pipeline import CoveragePipeline, CoverageStatus


def process_single_pdf(pdf_path: str) -> Dict:
    """
    يُعالج ملف PDF واحداً ويعيد قاموساً بكل المقاييس.
    لا ينهار أبداً — يمسك الاستثناءات ويُسجل الخطأ.
    """
    start_time = time.time()
    result = {
        "filename": os.path.basename(pdf_path),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "gate": "ERROR",
        "score": 0.0,
        "status": "ERROR",
        "rooms": 0,
        "detectors": 0,
        "coverage_pct": 0.0,
        "ceiling_height_m": 0.0,
        "violations_count": 0,
        "warnings": "",
        "requires_pe_review": True,
        "errors": "",
        "duration_sec": 0.0,
    }

    try:
        # ── المرحلة 1: Input Pipeline ──
        input_pipeline = InputPipeline(pdf_path)
        pipeline_result = input_pipeline.execute()

        result["gate"] = pipeline_result.status.value
        result["score"] = pipeline_result.drawing_score
        result["rooms"] = len(pipeline_result.rooms)
        result["detectors"] = len(pipeline_result.detectors)
        result["ceiling_height_m"] = pipeline_result.ceiling_height_m
        result["requires_pe_review"] = pipeline_result.requires_pe_review

        if pipeline_result.errors:
            result["errors"] = "; ".join(pipeline_result.errors)

        # إذا رُفض الرسم، لا نكمل للمحرك
        if pipeline_result.status == PipelineStatus.REJECTED:
            result["status"] = "REJECTED"
            result["warnings"] = "Drawing rejected at input gate"
            result["duration_sec"] = round(time.time() - start_time, 2)
            return result

        # ── المرحلة 2: Coverage Pipeline ──
        coverage = CoveragePipeline(pipeline_result)
        report = coverage.execute()

        result["status"] = report.status.value
        result["coverage_pct"] = (
            sum(r.coverage_pct for r in report.room_reports) / max(len(report.room_reports), 1)
            if report.room_reports else 0.0
        )

        # جمع التحذيرات
        all_warnings = list(report.global_warnings)
        if report.errors:
            all_warnings.extend(report.errors)
        result["warnings"] = "; ".join(all_warnings)

        # عدد الـ violations (إن وُجدت)
        violations_list = []
        for rr in report.room_reports:
            if hasattr(rr, 'warnings'):
                violations_list.extend(rr.warnings)
        result["violations_count"] = len(violations_list)

        if report.errors:
            if result["errors"]:
                result["errors"] += "; " + "; ".join(report.errors)
            else:
                result["errors"] = "; ".join(report.errors)

    except FileNotFoundError as e:
        result["errors"] = f"File not found: {e}"
        result["status"] = "ERROR"
    except Exception as e:
        result["errors"] = f"Exception: {type(e).__name__}: {e}"
        result["status"] = "ERROR"

    result["duration_sec"] = round(time.time() - start_time, 2)
    return result


def run_analysis(input_dir: str, output_csv: str = "vv_results.csv") -> List[Dict]:
    """
    يُعالج كل ملفات PDF في مجلد، ويُخرج CSV.
    يعيد قائمة القواميس للمعالجة الإضافية.
    """
    pdf_files = list(Path(input_dir).glob("*.pdf"))
    if not pdf_files:
        print(f"❌ لم يُعثر على ملفات PDF في: {input_dir}")
        return []

    print(f"🔍 بدء تحليل {len(pdf_files)} ملف PDF...")
    results = []

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"  [{i}/{len(pdf_files)}] معالجة: {pdf_path.name} ...", end=" ")
        entry = process_single_pdf(str(pdf_path))
        results.append(entry)
        print(f"→ {entry['status']} (gate: {entry['gate']}, score: {entry['score']:.2f})")

    # كتابة CSV
    fieldnames = [
        "filename", "timestamp_utc", "gate", "score", "status",
        "rooms", "detectors", "coverage_pct", "ceiling_height_m",
        "violations_count", "warnings", "requires_pe_review", "errors", "duration_sec"
    ]

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✅ اكتمل التحليل. النتائج محفوظة في: {output_file}")
    print(f"   إجمالي الملفات: {len(results)}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] in ("FAIL", "REJECTED", "ERROR"))
    caution = sum(1 for r in results if r["status"] in ("CAUTION", "REQUIRES PE REVIEW"))
    print(f"   PASS: {passed}, CAUTION/PE: {caution}, FAIL/REJECT/ERROR: {failed}")

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_vv_analysis.py /path/to/pdf/folder/ [--output results.csv]")
        sys.exit(1)

    input_directory = sys.argv[1]
    output_file = "vv_results.csv"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]

    if not os.path.isdir(input_directory):
        print(f"❌ المجلد غير موجود: {input_directory}")
        sys.exit(1)

    run_analysis(input_directory, output_file)