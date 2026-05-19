"""
reporting/html_report.py
========================
Generates a single-file, self-contained HTML report for review.

No external dependencies — uses inline CSS + base64-embedded overlay images.
Open the file in any browser, send via email, attach to project records.
"""
from __future__ import annotations
import base64, html, json
from dataclasses import asdict
from pathlib import Path
from typing import Optional


_CSS = """
:root{--c-crit:#c0392b;--c-maj:#e67e22;--c-min:#f1c40f;--c-adv:#3498db;
       --c-ok:#27ae60;--c-bg:#0e1116;--c-card:#1a1f27;--c-text:#e6edf3;
       --c-mut:#8b949e}
*{box-sizing:border-box}
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:var(--c-bg);
     color:var(--c-text);margin:0;padding:24px}
h1,h2,h3{margin:0 0 8px}
h1{font-size:22px} h2{font-size:18px;margin-top:24px;border-bottom:1px solid #333;padding-bottom:6px}
.card{background:var(--c-card);border-radius:8px;padding:16px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.k{color:var(--c-mut);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.v{font-size:22px;font-weight:600;margin-top:4px}
.sev{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;
     font-weight:700;text-transform:uppercase;color:#fff}
.sev.critical{background:var(--c-crit)} .sev.major{background:var(--c-maj)}
.sev.minor{background:var(--c-min);color:#000} .sev.advisory{background:var(--c-adv)}
.sev.info{background:#555}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #2a2f37;vertical-align:top}
th{color:var(--c-mut);font-weight:500;font-size:12px;text-transform:uppercase}
tr:hover td{background:#222831}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;background:#333;font-size:11px}
.match{color:var(--c-ok)} .over{color:var(--c-maj)} .under{color:var(--c-crit)}
.missing_on_drawing{color:var(--c-crit)} .not_in_schedule{color:var(--c-adv)}
.warn{background:#3a2a13;border-left:3px solid var(--c-maj);padding:8px 12px;margin:6px 0;
      border-radius:0 4px 4px 0;color:#fdd}
img.ovl{max-width:100%;border-radius:6px;margin-top:8px;border:1px solid #333}
footer{color:var(--c-mut);font-size:12px;text-align:center;margin-top:32px}
"""


def generate_report_html(report, overlay_paths: list[str] | None = None,
                         out_path: str = "report.html") -> str:
    overlay_paths = overlay_paths or []
    crit  = sum(1 for f in report.findings if f["severity"] == "critical")
    maj   = sum(1 for f in report.findings if f["severity"] == "major")
    parts = [f"<!doctype html><html><head><meta charset='utf-8'>"
             f"<title>EDA Report — {html.escape(report.file)}</title>"
             f"<style>{_CSS}</style></head><body>"]

    parts.append(f"<h1>Elite Drawing Analyzer — Report</h1>")
    parts.append(f"<div class='k'>FILE</div><div style='font-size:16px'>"
                 f"{html.escape(report.file)}  <span class='badge'>{report.file_type}</span></div>"
                 f"<div class='k' style='margin-top:6px'>SHA-256</div>"
                 f"<div style='font-family:monospace;font-size:11px;color:var(--c-mut)'>{report.file_sha}</div>")

    # Top KPI grid
    parts.append("<div class='grid' style='margin-top:16px'>"
                 f"{_kpi('Pages', report.summary.get('pages',1))}"
                 f"{_kpi('Layers', report.summary.get('layers',0))}"
                 f"{_kpi('Blocks', report.summary.get('blocks',0))}"
                 f"{_kpi('Elements', report.summary.get('entities',0))}"
                 f"{_kpi('Classified', sum(report.counts.values()))}"
                 f"{_kpi('Findings', len(report.findings))}"
                 f"{_kpi('Critical', crit, danger=crit>0)}"
                 f"{_kpi('Major', maj, danger=maj>0)}"
                 "</div>")

    # Counts table
    parts.append("<h2>Classified counts</h2><div class='card'><table>")
    parts.append("<tr><th>Symbol</th><th>Count</th></tr>")
    for sym, n in sorted(report.counts.items(), key=lambda kv: -kv[1]):
        parts.append(f"<tr><td>{html.escape(sym)}</td><td>{n}</td></tr>")
    parts.append("</table></div>")

    # Findings
    if report.findings:
        parts.append("<h2>⚠️ Compliance findings</h2><div class='card'><table>")
        parts.append("<tr><th>Severity</th><th>Code</th><th>Rule</th><th>Message</th>"
                     "<th>Recommendation</th></tr>")
        for f in report.findings:
            parts.append(f"<tr><td><span class='sev {f['severity']}'>{f['severity']}</span></td>"
                         f"<td>{html.escape(f['code'])}</td>"
                         f"<td>{html.escape(f['rule'])}</td>"
                         f"<td>{html.escape(f['message'])}<br>"
                         f"<small style='color:var(--c-mut)'>{html.escape(f.get('citation',''))}</small></td>"
                         f"<td>{html.escape(f.get('recommendation','')) }</td></tr>")
        parts.append("</table></div>")

    # Reconciliation
    if report.reconciliation:
        parts.append("<h2>📋 Schedule reconciliation (الحصر vs الرسم)</h2>"
                     "<div class='card'><table>")
        parts.append("<tr><th>Item</th><th>Scheduled</th><th>On drawing</th>"
                     "<th>Δ</th><th>Status</th></tr>")
        for r in report.reconciliation:
            parts.append(f"<tr><td>{html.escape(r['item'])}</td>"
                         f"<td>{r['scheduled_qty']}</td>"
                         f"<td>{r['actual_qty']}</td>"
                         f"<td>{r['delta']:+d}</td>"
                         f"<td class='{r['status']}'>{r['status']}</td></tr>")
        parts.append("</table></div>")

    # Warnings
    if report.warnings:
        parts.append("<h2>Warnings</h2>")
        for w in report.warnings:
            parts.append(f"<div class='warn'>{html.escape(w)}</div>")

    # Overlays
    if overlay_paths:
        parts.append("<h2>Annotated overlays</h2>")
        for p in overlay_paths:
            try:
                b64 = base64.b64encode(Path(p).read_bytes()).decode()
                parts.append(f"<div class='card'><div class='k'>{html.escape(Path(p).name)}</div>"
                             f"<img class='ovl' src='data:image/png;base64,{b64}'></div>")
            except Exception:
                continue

    parts.append("<footer>Elite Drawing Analyzer — every finding requires human verification "
                 "by a licensed engineer.</footer></body></html>")

    Path(out_path).write_text("".join(parts), encoding="utf-8")
    return out_path


def _kpi(label, value, danger=False):
    color = "var(--c-crit)" if danger else "var(--c-text)"
    return (f"<div class='card'><div class='k'>{label}</div>"
            f"<div class='v' style='color:{color}'>{value}</div></div>")
