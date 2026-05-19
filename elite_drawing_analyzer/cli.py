"""
cli.py — v0.2 with reporting + active learning
==============================================

Commands:
  analyze     run full pipeline on a file
  teach       add a labelled symbol example
  review      list low-confidence decisions awaiting human verification
  feedback    confirm or correct a decision (closes the learning loop)
  metrics     show learning-loop accuracy by confidence bucket
  stats       KB row counts
  symbols     list known symbols
  rules       list code rules
"""
from __future__ import annotations
import argparse, json, logging, sys
from pathlib import Path

from .pipeline import analyze_file, teach
from .intelligence.knowledge_base import KnowledgeBase
from .intelligence.active_learning import review_pending, submit_feedback, metrics


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="eda", description="Elite Drawing Analyzer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="Analyze a drawing file")
    a.add_argument("file")
    a.add_argument("--schedule", help="JSON list of {item,qty} — overrides auto-extraction")
    a.add_argument("--no-auto-schedule", action="store_true",
                   help="Disable automatic schedule table extraction from PDFs")
    a.add_argument("--json", help="Write full report JSON here")
    a.add_argument("--html", help="Write self-contained HTML report here")
    a.add_argument("--overlays", help="Directory to write annotated overlay PNGs")
    a.add_argument("--units-to-m", type=float, default=0.001)
    a.add_argument("--no-ocr", action="store_true")

    t = sub.add_parser("teach"); t.add_argument("image"); t.add_argument("symbol")

    r = sub.add_parser("review", help="List low-confidence decisions awaiting review")
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--max-conf", type=float, default=0.6)
    r.add_argument("--file-sha", help="Restrict to a specific file")

    fb = sub.add_parser("feedback")
    fb.add_argument("decision_id", type=int)
    fb.add_argument("--correct", action="store_true", help="Confirm prediction was correct")
    fb.add_argument("--correction", help="Right symbol name (if predicted was wrong)")
    fb.add_argument("--crop", help="Path to crop image (so the system can learn)")

    sub.add_parser("metrics", help="Show learning-loop accuracy")
    sub.add_parser("stats")
    sub.add_parser("symbols")
    sub.add_parser("rules")

    args = ap.parse_args()
    kb = KnowledgeBase()

    if args.cmd == "analyze":
        sched = json.loads(Path(args.schedule).read_text()) if args.schedule else None
        rep = analyze_file(args.file, kb=kb, schedule=sched,
                           auto_schedule=not args.no_auto_schedule,
                           units_to_m=args.units_to_m, do_ocr=not args.no_ocr,
                           overlay_dir=args.overlays, html_out=args.html)
        rep.print_summary()
        if args.json: rep.save_json(args.json); print(f"\nJSON → {args.json}")
        if args.html:                              print(f"HTML → {args.html}")
        if args.overlays:                          print(f"Overlays → {args.overlays}/")

    elif args.cmd == "teach":
        print(json.dumps(teach(kb, args.image, args.symbol), indent=2))

    elif args.cmd == "review":
        rows = review_pending(kb, limit=args.limit,
                              max_confidence=args.max_conf, file_sha=args.file_sha)
        if not rows: print("Nothing pending."); return
        print(f"{'ID':>6}  {'Conf':>5}  {'Symbol':22}  Page  Bbox")
        for r in rows:
            print(f"{r['id']:>6}  {r['confidence']:>5.2f}  {r['predicted_symbol']:22} "
                  f"  {r['page']:>3}  {r['bbox']}")

    elif args.cmd == "feedback":
        if not args.correct and not args.correction:
            print("Provide --correct or --correction NAME"); sys.exit(2)
        res = submit_feedback(kb, args.decision_id,
                              is_correct=args.correct,
                              correction=args.correction,
                              crop_image_path=args.crop)
        print(json.dumps(res, indent=2))

    elif args.cmd == "metrics":
        print(json.dumps(metrics(kb), indent=2))

    elif args.cmd == "stats":
        print(json.dumps(kb.stats(), indent=2))

    elif args.cmd == "symbols":
        for s in kb.list_symbols():
            print(f"  {s['name']:25} cat={s['category']:10} "
                  f"spacing={s['standard_spacing_m']}m  radius={s['coverage_radius_m']}m")

    elif args.cmd == "rules":
        for r in kb.conn.execute("SELECT code,rule_key,value,units,citation FROM rules ORDER BY code,rule_key"):
            print(f"  [{r['code']:8}] {r['rule_key']:42} = {r['value']} {r['units']:5}  ({r['citation']})")


if __name__ == "__main__":
    main()
