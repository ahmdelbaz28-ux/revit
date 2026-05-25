"""
workflow/end_to_end.py
======================
Complete workflow orchestrator — chains every bridge into one operation.

Use case:
  Engineer exports IFC from Revit → calls workflow → gets back:
    • Sealed engineering report (HTML + PDF + JSON + Markdown)
    • Marked-up DXF (overlay findings on AutoCAD geometry)
    • Revit command file (re-apply findings as Revit parameters + view filters)
    • IFC export ready for DIALux import
    • IES files for any synthetic luminaires
"""
from __future__ import annotations
import json, logging, os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..pipeline import analyze_file
from ..knowledge.memory import KnowledgeBase
from ..reporting.comprehensive_report import (
    build_full_report, render_html, render_markdown, render_json, render_pdf)
from ..bridges.autocad import write_findings_to_dxf
from ..bridges.revit   import (ifc_to_twin, write_revit_commands,
                                write_revit_addin_template)
from ..bridges.dialux  import make_ies, twin_to_ifc

log = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    canonical_report:  dict
    artifacts:         dict           # file_kind → absolute path
    chain_root:        str


def run_full_workflow(input_file: str,
                      output_dir: str,
                      project_meta: Optional[dict] = None,
                      jurisdiction: str = "NFPA-default",
                      private_key_pem: Optional[bytes] = None,
                      sign: bool = False,
                      annotate_dxf: bool = True,
                      emit_revit_commands: bool = True,
                      emit_dialux_ifc: bool = True,
                      kb: Optional[KnowledgeBase] = None,
                      schedule: Optional[list[dict]] = None,
                      ) -> WorkflowResult:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    artifacts = {}

    # 1. Run analysis (V8: pattern submission for human review)
    log.info("workflow: analyzing %s …", input_file)
    kb = kb or KnowledgeBase()
    report = analyze_file(input_file, kb=kb, schedule=schedule)

    # 2. If input is IFC, also build a DigitalTwin from it
    twin = None
    if Path(input_file).suffix.lower() == ".ifc":
        try: twin = ifc_to_twin(input_file)
        except Exception as ex: log.warning("ifc_to_twin failed: %s", ex)

    # 3. Generate signing keypair if requested
    if sign and not private_key_pem:
        from ..reporting.integrity import generate_keypair_pem
        sk_pem, pk_pem = generate_keypair_pem()
        (out / "signing_key.PRIVATE.pem").write_bytes(sk_pem)
        (out / "signing_key.public.pem").write_bytes(pk_pem)
        private_key_pem = sk_pem
        artifacts["public_key"] = str(out / "signing_key.public.pem")

    # 4. Build canonical sealed report
    canonical = build_full_report(
        report,
        project_meta=project_meta,
        jurisdiction=jurisdiction,
        private_key_pem=private_key_pem,
        digital_twin=twin,
        learning_log=report.learning_outcome,
    )

    # 5. Render all formats
    artifacts["json"] = render_json(canonical, str(out / "report.json"))
    artifacts["md"]   = render_markdown(canonical, str(out / "report.md"))
    artifacts["html"] = render_html(canonical, str(out / "report.html"))
    try:
        artifacts["pdf"] = render_pdf(canonical, str(out / "report.pdf"))
    except Exception as ex:
        log.warning("PDF render skipped: %s", ex)

    # 6. AutoCAD overlay
    if annotate_dxf and Path(input_file).suffix.lower() == ".dxf":
        try:
            artifacts["annotated_dxf"] = write_findings_to_dxf(
                input_file, str(out / "annotated.dxf"),
                findings=canonical["findings"],
                elements=canonical["elements"])
        except Exception as ex:
            log.warning("DXF annotation failed: %s", ex)

    # 7. Revit commands
    if emit_revit_commands:
        artifacts["revit_commands"] = write_revit_commands(
            canonical, str(out / "fsg.commands.json"), twin=twin)
        artifacts["revit_addin_cs"] = write_revit_addin_template(
            str(out / "FSGRevitAddin.cs"))

    # 8. DIALux exchange
    if emit_dialux_ifc and twin is not None:
        try:
            artifacts["dialux_ifc"] = twin_to_ifc(
                twin, str(out / "for_dialux.ifc"))
        except Exception as ex:
            log.warning("DIALux IFC export failed: %s", ex)
        # Always emit a default emergency-light IES
        artifacts["ies_emlight"] = make_ies(str(out / "FSG_EMLIGHT.ies"))

    log.info("workflow complete — %d artifacts under %s", len(artifacts), out)
    return WorkflowResult(
        canonical_report=canonical,
        artifacts=artifacts,
        chain_root=canonical["integrity"]["chain_root"],
    )
