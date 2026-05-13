"""
core/tables.py
==============
Automatic table / legend / schedule extraction from PDFs.

Why: the classic "حصر" workflow is — engineer puts a table on sheet 1 with
'Item | Qty | Description', and we need to read it WITHOUT a human pasting
JSON.

Strategy:
  1. PyMuPDF native find_tables()   — works on digital PDFs
  2. Heuristic grid detection        — for vector tables not auto-detected
  3. OCR fallback                    — for scanned PDFs / images

Output: list of {"item": str, "qty": int, "raw": {...full row}}
"""
from __future__ import annotations
import logging, re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Column-name aliases — engineers spell these a thousand different ways
ITEM_COL = {"item","description","equipment","symbol","device","رمز","الصنف","البيان","الوصف"}
QTY_COL  = {"qty","quantity","count","no","number","nos","الكمية","العدد"}


def extract_schedule_from_pdf(path: str, page: int | None = None) -> list[dict]:
    """Try every backend in order; return first non-empty result.
    `page`: 0-indexed; None = scan all pages."""
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF required: pip install pymupdf")

    doc = fitz.open(path)
    pages = [page] if page is not None else range(doc.page_count)
    rows: list[dict] = []
    for pno in pages:
        pg = doc[pno]
        # 1) PyMuPDF native
        try:
            tables = pg.find_tables()
            for tbl in (tables.tables if hasattr(tables, "tables") else tables):
                rows.extend(_rows_from_pymupdf_table(tbl))
        except Exception as ex:
            log.debug("find_tables failed p%d: %s", pno, ex)

        if rows: continue

        # 2) Heuristic: parse text grid by coordinates
        rows.extend(_heuristic_grid(pg))

    # 3) OCR fallback
    if not rows:
        rows = _ocr_table_fallback(path)

    # Dedupe + clean
    out, seen = [], set()
    for r in rows:
        key = (r.get("item",""), r.get("qty",0))
        if key in seen or not r.get("item"): continue
        seen.add(key); out.append(r)
    log.info("Schedule extraction: %d rows from %s", len(out), Path(path).name)
    return out


def _rows_from_pymupdf_table(tbl) -> list[dict]:
    data = tbl.extract() if hasattr(tbl, "extract") else None
    if not data or len(data) < 2: return []
    header = [(c or "").strip().lower() for c in data[0]]
    item_idx = next((i for i,h in enumerate(header) if any(k in h for k in ITEM_COL)), None)
    qty_idx  = next((i for i,h in enumerate(header) if any(k in h for k in QTY_COL )), None)
    if item_idx is None or qty_idx is None: return []
    rows = []
    for r in data[1:]:
        try:
            item = (r[item_idx] or "").strip()
            qty  = _parse_qty(r[qty_idx])
            if item and qty is not None:
                rows.append({"item": item, "qty": qty,
                             "raw": dict(zip(header, r))})
        except Exception:
            continue
    return rows


def _heuristic_grid(page) -> list[dict]:
    """Group text spans by y-coord into rows, then by x into columns. Crude
    but works on engineering plan legends."""
    spans = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type",0) != 0: continue
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                t = sp["text"].strip()
                if t: spans.append((sp["bbox"][1], sp["bbox"][0], t))
    if len(spans) < 6: return []
    spans.sort()
    # cluster by y
    rows_y, cur, cur_y = [], [], None
    tol = 4.0
    for y,x,t in spans:
        if cur_y is None or abs(y-cur_y) < tol:
            cur.append((x,t)); cur_y = y if cur_y is None else cur_y
        else:
            rows_y.append(cur); cur=[(x,t)]; cur_y=y
    if cur: rows_y.append(cur)

    # find header row
    header_row = None
    for i,r in enumerate(rows_y):
        joined = " ".join(t for _,t in r).lower()
        if any(k in joined for k in ITEM_COL) and any(k in joined for k in QTY_COL):
            header_row = i; break
    if header_row is None: return []

    # establish column x-anchors from header
    header_sorted = sorted(rows_y[header_row])
    col_x = [x for x,_ in header_sorted]
    col_names = [t.lower() for _,t in header_sorted]
    item_col = next((i for i,n in enumerate(col_names) if any(k in n for k in ITEM_COL)), None)
    qty_col  = next((i for i,n in enumerate(col_names) if any(k in n for k in QTY_COL )), None)
    if item_col is None or qty_col is None: return []

    out = []
    for r in rows_y[header_row+1:]:
        cells = {i:"" for i in range(len(col_x))}
        for x,t in r:
            # snap to nearest column
            ci = min(range(len(col_x)), key=lambda i: abs(x-col_x[i]))
            cells[ci] = (cells[ci] + " " + t).strip()
        item = cells[item_col]
        qty  = _parse_qty(cells[qty_col])
        if item and qty is not None:
            out.append({"item": item, "qty": qty, "raw": cells})
    return out


def _ocr_table_fallback(path: str) -> list[dict]:
    """Render each page to image, OCR it, then look for 'item .... NUMBER' patterns."""
    try:
        import fitz, cv2
        from .ocr import run_ocr
    except Exception as ex:
        log.warning("OCR fallback unavailable: %s", ex); return []
    doc = fitz.open(path)
    out = []
    for pno, pg in enumerate(doc):
        pix = pg.get_pixmap(dpi=250)
        png = f"{path}.tab_p{pno}.png"
        pix.save(png)
        import numpy as np
        img = cv2.imread(png)
        if img is None: continue
        boxes = run_ocr(img)
        # group by y
        boxes.sort(key=lambda b: b.bbox[1])
        lines: list[list] = []
        cur = []
        prev_y = -999
        for b in boxes:
            y = b.bbox[1]
            if cur and abs(y - prev_y) > 18:
                lines.append(cur); cur=[]
            cur.append(b); prev_y = y
        if cur: lines.append(cur)
        for ln in lines:
            ln.sort(key=lambda b: b.bbox[0])
            text = " ".join(b.text for b in ln)
            m = re.search(r"^(.+?)\s+(\d{1,4})\s*$", text.strip())
            if m:
                item = m.group(1).strip()
                qty  = int(m.group(2))
                if 3 < len(item) < 60:
                    out.append({"item": item, "qty": qty, "raw": {"line": text, "page": pno}})
    return out


def _parse_qty(s) -> Optional[int]:
    if s is None: return None
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else None
