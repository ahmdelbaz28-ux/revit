"""
reporting/comprehensive_report.py
=================================
Build a FULL forensic engineering report from analysis output.

Sections produced (every one citation-backed, every one customizable):
  1. Cover & Identification (sealed hashes)
  2. Methodology — every algorithm used, with version
  3. Code Applicability Matrix — which NFPA/IBC/NEC clauses apply
  4. Evidence — every classified element with confidence
  5. Compliance Findings — per-rule, per-room
  6. Schedule Reconciliation
  7. Safety Gates — pass/fail
  8. Smoke Pre-Screening Estimate (if input populated)
  9. Engineering Calculations — panels, loops, voltage drop, conduit
 10. ADA Compliance Audit
 11. Pattern Submission Log — what was submitted for human review
 12. Reasoning Trace — every step the engine took, with inputs/outputs
 13. Honest Limitations — what we DIDN'T check
 14. Reviewer Sign-Off Block — for the licensed engineer
 15. Integrity Footer — chain root + signature

Output formats: HTML, Markdown, JSON, PDF (via weasyprint or fallback).
All driven by Jinja2 templates the USER can edit in `templates/`.
"""
from __future__ import annotations
import json, logging, os, shutil
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

from .integrity import seal_report

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


# ──────────────────────────────────────────────────────────────────────────
def build_full_report(report,
                      project_meta: Optional[dict] = None,
                      jurisdiction: str = "NFPA-default",
                      issuer: str = "FireSafetyGenius",
                      software_version: str = "1.1.0",
                      private_key_pem: Optional[bytes] = None,
                      engineering_results: Optional[dict] = None,
                      digital_twin = None,
                      learning_log: Optional[dict] = None) -> dict:
    """Assemble the canonical report dict (BEFORE rendering)."""
    project_meta = project_meta or {}

    findings_normalized = []
    for f in report.findings:
        item = dict(f) if isinstance(f, dict) else asdict(f)
        item.setdefault("category", "compliance")
        findings_normalized.append(item)

    # Add ADA findings if present
    for f in (engineering_results or {}).get("ada_findings", []):
        item = asdict(f) if is_dataclass(f) else dict(f)
        item["category"] = "ada"
        findings_normalized.append(item)

    # Add safety-gate failures as findings
    for gate in (engineering_results or {}).get("safety_gates", []):
        g = asdict(gate) if is_dataclass(gate) else dict(gate)
        if g.get("status") == "fail":
            findings_normalized.append({
                "category":"safety_gate", "severity":"critical",
                "rule": g["name"], "code":"SYSTEM",
                "message": f"Gate '{g['name']}' FAILED.",
                "evidence": {"findings": g.get("findings", [])},
                "citation":"FireSafetyGenius safety gate",
                "recommendation":"Review the underlying findings; cannot issue."})

    canonical = {
        "report_type": "FireSafety Engineering Assessment",
        "schema":      "fsg-report-1.0",
        "project": {
            "name":         project_meta.get("name","Untitled Project"),
            "address":      project_meta.get("address",""),
            "owner":        project_meta.get("owner",""),
            "consultant":   project_meta.get("consultant",""),
            "jurisdiction": jurisdiction,
            "occupancy":    project_meta.get("occupancy","business"),
            "sprinklered":  project_meta.get("sprinklered", True),
        },
        "source_file": {
            "name":        report.file,
            "type":        report.file_type,
            "sha256":      report.file_sha,
            "elapsed_s":   report.elapsed_seconds,
        },
        "methodology": _build_methodology(software_version),
        "code_matrix": _build_code_matrix(jurisdiction),
        "summary":     report.summary,
        "counts":      report.counts,
        "elements":    report.elements,
        "findings":    findings_normalized,
        "reconciliation": report.reconciliation,
        "warnings":    report.warnings,
        "ocr_texts":   report.ocr_texts[:200],   # cap for size
        "reasoning":   report.reasoning_trace,
        "learning":    report.learning_outcome,
        "engineering": engineering_results or {},
        "limitations": _honest_limitations(),
        "review_block": {
            "engineer_name":    "",
            "license_no":       "",
            "license_state":    "",
            "signature_date":   "",
            "engineer_seal":    "",
            "approval_status":  "PENDING_REVIEW",
            "approval_notes":   "",
        },
        "issuer":   issuer,
        "software": software_version,
    }

    # Pull twin summary if present
    if digital_twin is not None:
        canonical["digital_twin"] = {
            "rooms":    [asdict(r) for r in digital_twin.rooms.values()],
            "devices":  [asdict(d) for d in digital_twin.devices.values()],
            "openings": [asdict(o) for o in digital_twin.openings],
            "cables":   [asdict(c) for c in digital_twin.cables],
        }
    if learning_log:
        canonical["learning_log"] = learning_log

    # Seal with hash chain (+ signature if key provided)
    canonical = seal_report(canonical, issuer=issuer,
                            software_version=software_version,
                            private_key_pem=private_key_pem)
    return canonical


def _build_methodology(software_version) -> list[dict]:
    return [
        {"step":1, "name":"File Ingestion",
         "algorithm":"Multi-format (DXF/DWG/PDF/IFC/Image) → normalized entity model",
         "tools":["ezdxf","PyMuPDF","ifcopenshell","OpenCV"]},
        {"step":2, "name":"Raster Recovery",
         "algorithm":"CLAHE + bilateral filter + adaptive threshold + directional morphology",
         "purpose":"Heal broken/faded lines before classification"},
        {"step":3, "name":"OCR",
         "algorithm":"Tesseract / EasyOCR multilingual with deskew + upscale",
         "languages":["eng","ara"]},
        {"step":4, "name":"Symbol Classification",
         "algorithm":"3-tier: name pattern → embedding k-NN → geometric heuristic",
         "embedder":"HOG (default) / CLIP (optional)"},
        {"step":5, "name":"Pattern Review",
         "algorithm":"Submit patterns for FPE review via pattern_library "
                     "(no automatic learning)"},
        {"step":6, "name":"Compliance Check",
         "algorithm":"Rule-based against KB-stored NFPA/IBC/NEC values",
         "evidence":"Pairwise distance + coverage (Monte Carlo) + Voronoi gap"},
        {"step":7, "name":"Schedule Reconciliation",
         "algorithm":"Exact + alias + fuzzy match (cutoff 0.85, advisory log)"},
        {"step":8, "name":"Reasoning",
         "algorithm":"Decomposed chain-of-thought planner with weighted evidence"},
        {"step":9, "name":"Smoke Pre-Screening",
         "algorithm":"Pre-screening estimate (±50% error band)",
         "limitations":"NOT a simulation, NOT NFPA 92 compliant"},
        {"step":10,"name":"Integrity Sealing",
         "algorithm":"SHA-256 hash chain + optional Ed25519 signature",
         "purpose":"Tamper detection (NOT a claim of correctness)"},
    ]


def _build_code_matrix(jurisdiction) -> list[dict]:
    return [
        {"code":"NFPA 72", "edition":"2022", "applies":True,
         "scope":"Fire Alarm — detector spacing, notification, survivability"},
        {"code":"NFPA 13", "edition":"2022", "applies":True,
         "scope":"Sprinkler — spacing, coverage area, hazard classification"},
        {"code":"NFPA 101","edition":"2021", "applies":True,
         "scope":"Life Safety — egress, travel distance, common path"},
        {"code":"NFPA 92", "edition":"2021", "applies":True,
         "scope":"Smoke Control — used as inspiration for simulation; "
                  "not a substitute for engineered design"},
        {"code":"NEC",     "edition":"2023", "applies":True,
         "scope":"Electrical — ampacity, conduit fill, clearances"},
        {"code":"ICC A117.1","edition":"2017","applies":True,
         "scope":"Accessibility — mounting heights, reach ranges"},
        {"code":"NFPA 720","edition":"2019", "applies":False,
         "scope":"CO Detection — module not yet implemented"},
        {"code":"IBC",     "edition":"2021", "applies":True,
         "scope":"Building Construction — referenced via NFPA 101"},
    ]


def _honest_limitations() -> list[str]:
    return [
        "This software produces an ANALYSIS — not an engineered design.",
        "All findings require independent review by a licensed Professional Engineer "
        "before any construction or modification.",
        "Smoke pre-screening uses an analytical estimate and is NOT a substitute for "
        "CFD (e.g., FDS) for atriums, large open spaces, or compartmented designs.",
        "Pattern submissions are STORED but never automatically applied - "
        "FPE review is required.",
        "No claim of infallibility is made. The integrity seal proves the report "
        "has not been altered since issuance; it does not prove the underlying "
        "analysis is free of error.",
        "Backup power calculations, survivability ratings, and battery sizing are "
        "NOT performed by this software.",
        "Fire pump hydraulic calculations and standpipe sizing are NOT performed.",
        "Mass notification, BDA/DAS, and CO detection are NOT analyzed.",
    ]


# ──────────────────────────────────────────────────────────────────────────
# Renderers — Jinja2 templates from disk (USER CAN EDIT THEM)
# ──────────────────────────────────────────────────────────────────────────
def render_html(canonical: dict, out_path: str,
                template: str = "default.html.j2",
                template_dir: Path = TEMPLATE_DIR) -> str:
    env = _jinja_env(template_dir)
    tpl = env.get_template(template)
    html = tpl.render(r=canonical)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path


def render_markdown(canonical: dict, out_path: str,
                    template: str = "default.md.j2",
                    template_dir: Path = TEMPLATE_DIR) -> str:
    env = _jinja_env(template_dir)
    tpl = env.get_template(template)
    md = tpl.render(r=canonical)
    Path(out_path).write_text(md, encoding="utf-8")
    return out_path


def render_json(canonical: dict, out_path: str) -> str:
    Path(out_path).write_text(json.dumps(canonical, indent=2, default=str, ensure_ascii=False))
    return out_path


def render_pdf(canonical: dict, out_path: str,
               html_template: str = "default.html.j2") -> str:
    """HTML → PDF via weasyprint. Falls back to writing HTML if weasyprint missing."""
    try:
        from weasyprint import HTML
        html_path = out_path + ".tmp.html"
        render_html(canonical, html_path, template=html_template)
        HTML(html_path).write_pdf(out_path)
        os.unlink(html_path)
        return out_path
    except ImportError:
        log.warning("weasyprint not installed — writing HTML instead of PDF")
        return render_html(canonical, out_path.replace(".pdf",".html"),
                           template=html_template)


def _jinja_env(template_dir: Path):
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        raise RuntimeError("Jinja2 required: pip install jinja2")
    return Environment(loader=FileSystemLoader(str(template_dir)),
                       autoescape=select_autoescape(["html","xml","j2"]),
                       trim_blocks=True, lstrip_blocks=True)


# ──────────────────────────────────────────────────────────────────────────
# User template management
# ──────────────────────────────────────────────────────────────────────────
def export_default_templates(dest_dir: str) -> list[str]:
    """Copy bundled templates to a user-writable directory so they can edit."""
    dest = Path(dest_dir); dest.mkdir(parents=True, exist_ok=True)
    out = []
    for src in TEMPLATE_DIR.iterdir():
        if src.is_file() and src.suffix.lower() in (".j2", ".css"):
            dst = dest / src.name
            shutil.copy(src, dst)
            out.append(str(dst))
    return out


def list_template_variables() -> dict:
    """Documentation of every {{ variable }} the template can use."""
    return {
        "r.project.name":              "Project name (str)",
        "r.project.address":           "Project address (str)",
        "r.project.jurisdiction":      "Code jurisdiction (str)",
        "r.source_file.name":          "Original drawing filename",
        "r.source_file.sha256":        "Cryptographic file hash",
        "r.methodology[]":             "List of 10 methodology steps",
        "r.code_matrix[]":             "List of applicable code editions",
        "r.counts":                    "Dict of {symbol: count}",
        "r.findings[]":                "List of compliance/ADA findings with hashes",
        "r.reconciliation[]":          "Schedule vs drawing items",
        "r.engineering.panel_plan":    "Panel optimizer output",
        "r.engineering.loop_plan":     "Loop designer output",
        "r.engineering.smoke_estimator": "Smoke pre-screening estimate",
        "r.patterns":                  "Pattern submissions for review",
        "r.limitations[]":             "Honest list of what was NOT checked",
        "r.review_block":              "Reviewer sign-off fields (editable)",
        "r.integrity":                 "Hash chain root + signature",
    }
