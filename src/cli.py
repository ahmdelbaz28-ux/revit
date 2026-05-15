"""
cli.py — FireSafetyGenius v1.1 command-line interface
======================================================

⚠️ LIFE-SAFETY WARNING ⚠️
======================================================

This system outputs fire safety recommendations.

⚠️ IMPORANT: All outputs require PE verification.
⚠️ OUTPUTS NOT VERIFIED by licensed PE may result in death.
⚠️ Use only within validated scope (see docs/SCOPE_DOCUMENT.md)
"""

from __future__ import annotations
import argparse, json, logging, sys, csv
from pathlib import Path

from . import __version__
try:
    from .pipeline import analyze_file
except ImportError:
    analyze_file = None
from .knowledge.memory        import KnowledgeBase
# V8: self_learner disabled - use pattern_library instead
# from .knowledge.self_learner  import SelfLearner
from .knowledge.active_learning import review_pending, submit_feedback, metrics
from .engineering.panel_optimizer import optimize_panels, recommend_panel_count
from .engineering.loop_designer   import design_loops
from .engineering.nec_tables      import voltage_drop, select_conduit, select_minimum_awg
from .engineering.ada_check       import audit_devices
# V8: smoke_simulator disabled - use smoke_estimator instead
# from .digital_twin.smoke_simulator import simulate, FireScenario
from .reporting.comprehensive_report import (
    build_full_report, render_html, render_markdown, render_json, render_pdf,
    export_default_templates, list_template_variables)
from .reporting.integrity import verify_seal, generate_keypair_pem
from .workflow.end_to_end import run_full_workflow


def _read_xy_csv(p):
    out = []
    with open(p) as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#"): continue
            out.append((float(row[0]), float(row[1])))
    return out


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="fsg",
                                  description=f"FireSafetyGenius v{__version__}")
    ap.add_argument("--version", action="version", version=f"FSG v{__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # ── analyze ──
    a = sub.add_parser("analyze");           a.add_argument("file")
    a.add_argument("--schedule"); a.add_argument("--no-auto-schedule", action="store_true")
    a.add_argument("--json"); a.add_argument("--html"); a.add_argument("--overlays")
    a.add_argument("--units-to-m", type=float, default=0.001)
    a.add_argument("--no-ocr", action="store_true")
    a.add_argument("--no-learn", action="store_true")

    # ── workflow (NEW v1.1) ──
    w = sub.add_parser("workflow",
        help="Run full end-to-end pipeline → all artifacts (HTML/PDF/MD/JSON + DXF + Revit commands + IES)")
    w.add_argument("file")
    w.add_argument("--out", required=True, help="Output directory")
    w.add_argument("--project-name", default="Untitled")
    w.add_argument("--address", default="")
    w.add_argument("--owner",   default="")
    w.add_argument("--consultant", default="")
    w.add_argument("--jurisdiction", default="NFPA-default")
    w.add_argument("--occupancy", default="business")
    w.add_argument("--sign", action="store_true",
                   help="Generate ed25519 signing keypair and sign report")
    w.add_argument("--schedule", help="JSON list of {item,qty}")

    # ── report (NEW v1.1) ──
    rp = sub.add_parser("report",
        help="Build a comprehensive report from a JSON analysis output")
    rp.add_argument("json_in", help="Analysis JSON (from `analyze --json`)")
    rp.add_argument("--out", required=True, help="Output directory")
    rp.add_argument("--template", default="default.html.j2")
    rp.add_argument("--template-dir", help="Custom template directory")
    rp.add_argument("--sign", action="store_true")

    # ── templates export (NEW v1.1) ──
    tp = sub.add_parser("templates", help="Manage report templates")
    tp_sub = tp.add_subparsers(dest="t_action", required=True)
    te = tp_sub.add_parser("export")
    te.add_argument("dir")
    tl = tp_sub.add_parser("list-vars")

    # ── verify-seal (NEW v1.1) ──
    vs = sub.add_parser("verify-seal",
        help="Verify cryptographic integrity of a sealed report.json")
    vs.add_argument("json_file")

    # ── keygen ──
    sub.add_parser("keygen", help="Generate ed25519 keypair for signing")

    # Existing commands
    sub.add_parser("learned")
    p = sub.add_parser("panel-optimize"); p.add_argument("xy_csv")
    p.add_argument("--k", type=int, default=0); p.add_argument("--max-devices", type=int, default=99)
    p.add_argument("--max-run-m", type=float, default=500.0)
    l = sub.add_parser("loop-design"); l.add_argument("xy_csv")
    l.add_argument("--panel-x", type=float, default=0.0); l.add_argument("--panel-y", type=float, default=0.0)
    l.add_argument("--max-devices", type=int, default=99); l.add_argument("--max-len-m", type=float, default=760.0)
    l.add_argument("--class-a", action="store_true")
    s = sub.add_parser("simulate")
    s.add_argument("volume_m3", type=float); s.add_argument("ceiling_m", type=float)
    s.add_argument("--device-h", type=float, default=2.8); s.add_argument("--growth", default="medium")
    ad = sub.add_parser("ada"); ad.add_argument("devices_json")
    v = sub.add_parser("vdrop")
    v.add_argument("length_m", type=float); v.add_argument("amps", type=float); v.add_argument("awg", type=int)
    v.add_argument("--supply-v", type=float, default=24.0); v.add_argument("--min-pct", type=float, default=0.70)
    r = sub.add_parser("review"); r.add_argument("--limit", type=int, default=20); r.add_argument("--max-conf", type=float, default=0.6)
    fb = sub.add_parser("feedback"); fb.add_argument("decision_id", type=int)
    fb.add_argument("--correct", action="store_true"); fb.add_argument("--correction"); fb.add_argument("--crop")
    sub.add_parser("metrics"); sub.add_parser("stats")
    sub.add_parser("symbols"); sub.add_parser("rules")

    args = ap.parse_args()
    kb = KnowledgeBase()

    if args.cmd == "analyze":
        sched = json.loads(Path(args.schedule).read_text()) if args.schedule else None
        rep = analyze_file(args.file, kb=kb, schedule=sched,
                           auto_schedule=not args.no_auto_schedule,
                           units_to_m=args.units_to_m, do_ocr=not args.no_ocr,
                           do_pattern_review=False,  # V8: disabled by default
                           overlay_dir=args.overlays, html_out=args.html)
        rep.print_summary()
        if args.json: rep.save_json(args.json); print(f"JSON → {args.json}")

    elif args.cmd == "workflow":
        sched = json.loads(Path(args.schedule).read_text()) if args.schedule else None
        res = run_full_workflow(
            args.file, args.out, kb=kb, schedule=sched,
            project_meta={"name":args.project_name,"address":args.address,
                          "owner":args.owner,"consultant":args.consultant,
                          "occupancy":args.occupancy,"sprinklered":True},
            jurisdiction=args.jurisdiction, sign=args.sign)
        print(f"\n✓ Workflow complete")
        print(f"  Chain root: {res.chain_root[:32]}…")
        for k, p in res.artifacts.items():
            print(f"  {k:18}  {p}")

    elif args.cmd == "report":
        canonical = json.loads(Path(args.json_in).read_text())
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        kw = {}
        if args.template_dir: kw["template_dir"] = Path(args.template_dir)
        render_html(canonical, str(out/"report.html"),
                    template=args.template, **kw)
        render_markdown(canonical, str(out/"report.md"), **kw)
        render_json(canonical, str(out/"report.json"))
        print(f"✓ Reports → {out}/")

    elif args.cmd == "templates":
        if args.t_action == "export":
            paths = export_default_templates(args.dir)
            for p in paths: print(f"✓ {p}")
            print(f"\nEdit them in your editor, then pass --template-dir to "
                  f"`fsg report` to use your customized version.")
        elif args.t_action == "list-vars":
            vars_ = list_template_variables()
            for k, v in vars_.items(): print(f"  {k:35} {v}")

    elif args.cmd == "verify-seal":
        report = json.loads(Path(args.json_file).read_text())
        res = verify_seal(report)
        if res["ok"]:
            print(f"✓ Chain valid")
            if res["signature_ok"] is True:
                print(f"✓ Signature valid (Ed25519)")
            elif res["signature_ok"] is False:
                print(f"✗ SIGNATURE INVALID — report is tampered!"); sys.exit(2)
            else:
                print(f"  No signature present (chain-only integrity)")
        else:
            print(f"✗ TAMPERING DETECTED: {res['details']}"); sys.exit(2)

    elif args.cmd == "keygen":
        sk, pk = generate_keypair_pem()
        Path("fsg_signing.PRIVATE.pem").write_bytes(sk)
        Path("fsg_signing.public.pem").write_bytes(pk)
        print("✓ fsg_signing.PRIVATE.pem  (KEEP SECRET)")
        print("✓ fsg_signing.public.pem   (share for verification)")

    elif args.cmd == "learned":
        # V8: disabled - use pattern_library instead
        print("V8: Pattern review disabled by default. Use pattern_library for human-curated patterns.")
        # print(json.dumps(SelfLearner(kb).explain_what_i_learned(), indent=2, default=str))

    elif args.cmd == "panel-optimize":
        pts = _read_xy_csv(args.xy_csv)
        k = args.k or recommend_panel_count(pts, max_devices_per_panel=args.max_devices,
                                            max_single_run_m=args.max_run_m)
        plan = optimize_panels(pts, k=k, max_devices_per_panel=args.max_devices,
                                max_single_run_m=args.max_run_m)
        for p in plan.panels:
            print(f"{p.id} pos={p.position} devices={p.device_count} cable={p.total_cable_m:.0f}m")
        for w in plan.warnings: print(f"⚠ {w}")
        print(f"TOTAL CABLE: {plan.total_cable_m:.0f} m")

    elif args.cmd == "loop-design":
        pts = _read_xy_csv(args.xy_csv)
        plan = design_loops(pts, (args.panel_x, args.panel_y),
                            max_devices_per_loop=args.max_devices,
                            max_loop_length_m=args.max_len_m, class_a=args.class_a)
        for loop in plan.loops:
            print(f"{loop.id} devices={len(loop.order)} length={loop.total_length_m}m")
        for w in plan.warnings: print(f"⚠ {w}")

    elif args.cmd == "simulate":
        # V8: disabled - use smoke_estimator instead
        print("V8: Smoke pre-screening disabled. Use v8_core.smoke_estimator for estimates.")
        # res = simulate(args.volume_m3, args.ceiling_m,
        #                 device_mount_height_m=args.device_h,
        #                 scenario=FireScenario.named(args.growth))
        # print(json.dumps(res.__dict__, indent=2, default=str))

    elif args.cmd == "ada":
        for f in audit_devices(json.loads(Path(args.devices_json).read_text())):
            print(f"[{f.severity:8}] {f.rule}: {f.message}")

    elif args.cmd == "vdrop":
        r = voltage_drop(args.length_m, args.amps, args.awg,
                         supply_v=args.supply_v, min_pct_remaining=args.min_pct)
        print(json.dumps(r.__dict__, indent=2, default=str))

    elif args.cmd == "review":
        rows = review_pending(kb, limit=args.limit, max_confidence=args.max_conf)
        if not rows: print("Nothing pending."); return
        for r in rows:
            print(f"{r['id']:>6}  conf={r['confidence']:.2f}  {r['predicted_symbol']:22}")
    elif args.cmd == "feedback":
        if not args.correct and not args.correction:
            print("Use --correct OR --correction"); sys.exit(2)
        print(json.dumps(submit_feedback(kb, args.decision_id,
                          is_correct=args.correct, correction=args.correction,
                          crop_image_path=args.crop), indent=2))
    elif args.cmd == "metrics":  print(json.dumps(metrics(kb), indent=2))
    elif args.cmd == "stats":    print(json.dumps(kb.stats(), indent=2))
    elif args.cmd == "symbols":
        for s in kb.list_symbols():
            print(f"  {s['name']:25} cat={s['category']:10}")
    elif args.cmd == "rules":
        for r in kb.conn.execute("SELECT code,rule_key,value,units,citation FROM rules"):
            print(f"  [{r['code']:8}] {r['rule_key']:42} = {r['value']} {r['units']}")


if __name__ == "__main__":
    main()
