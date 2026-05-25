"""
core/ingest.py
==============
Universal file ingestion. Detects file type and routes to the right reader.
Returns a normalized in-memory representation: NormalizedDrawing.

Supported (with graceful degradation if optional deps missing):
  - DXF        (ezdxf)
  - DWG        (via Teigha/ODA File Converter shell call, or libredwg if installed)
  - PDF        (PyMuPDF: both vector ops and rasterized pages)
  - IFC / BIM  (ifcopenshell)
  - Images     (OpenCV)  — JPG/PNG/TIFF (including scanned/faded)

Philosophy:
  - NEVER silently drop data. Anything we can't classify goes into raw_unknown
    so the reasoning layer can still flag it.
  - Every entity carries provenance: source_file, page, layer, block, bbox, confidence.
"""
from __future__ import annotations
import os, hashlib, mimetypes, logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from pathlib import Path

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Normalized data model — every backend speaks THIS language
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Entity:
    """One geometric/textual element on a drawing."""
    kind: str                       # 'line','polyline','arc','circle','text','block_ref','image_region','symbol'
    geom: dict                      # geometry primitives (coords, radius, etc.)
    layer: str = "0"
    block: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    bbox: Optional[tuple] = None    # (x0,y0,x1,y1) in drawing units
    text: Optional[str] = None
    page: int = 0
    confidence: float = 1.0         # 1.0 for clean vector, <1 for OCR / recovered
    provenance: dict = field(default_factory=dict)


@dataclass
class NormalizedDrawing:
    source_path: str
    source_sha256: str
    file_type: str                  # 'dxf','dwg','pdf','ifc','image'
    units: str = "mm"               # best-effort
    page_count: int = 1
    layers: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    raw_unknown: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def summary(self) -> dict:
        from collections import Counter
        return {
            "file": os.path.basename(self.source_path),
            "type": self.file_type,
            "pages": self.page_count,
            "layers": len(self.layers),
            "blocks": len(self.blocks),
            "entities": len(self.entities),
            "by_kind": dict(Counter(e.kind for e in self.entities)),
            "by_layer": dict(Counter(e.layer for e in self.entities)),
            "unknown_blobs": len(self.raw_unknown),
        }


# ──────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────
def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_type(path: str) -> str:
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in {"dxf"}: return "dxf"
    if ext in {"dwg"}: return "dwg"
    if ext in {"pdf"}: return "pdf"
    if ext in {"ifc"}: return "ifc"
    if ext in {"jpg","jpeg","png","tif","tiff","bmp","webp"}: return "image"
    # fallback: peek bytes
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"%PDF"): return "pdf"
    if head[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"): return "image"
    return "unknown"


def ingest(path: str) -> NormalizedDrawing:
    ftype = detect_type(path)
    nd = NormalizedDrawing(
        source_path=os.path.abspath(path),
        source_sha256=sha256_of(path),
        file_type=ftype,
    )
    log.info("Ingesting %s as %s", path, ftype)

    if   ftype == "dxf":   _ingest_dxf(path, nd)
    elif ftype == "dwg":   _ingest_dwg(path, nd)
    elif ftype == "pdf":   _ingest_pdf(path, nd)
    elif ftype == "ifc":   _ingest_ifc(path, nd)
    elif ftype == "image": _ingest_image(path, nd)
    else:
        raise ValueError(f"Unsupported file type: {ftype}")
    return nd


# ──────────────────────────────────────────────────────────────────────────
# DXF — full vector, layers, blocks, attributes
# ──────────────────────────────────────────────────────────────────────────
def _ingest_dxf(path: str, nd: NormalizedDrawing) -> None:
    try:
        import ezdxf
    except ImportError:
        raise RuntimeError("ezdxf not installed. pip install ezdxf")

    doc = ezdxf.readfile(path)
    nd.units = {0:"unitless",1:"in",2:"ft",4:"mm",5:"cm",6:"m"}.get(doc.header.get("$INSUNITS",4),"mm")
    nd.layers = [{"name": l.dxf.name, "color": l.dxf.color, "frozen": l.is_frozen()} for l in doc.layers]
    nd.blocks = [{"name": b.name, "entity_count": len(list(b))} for b in doc.blocks if not b.name.startswith("*")]

    msp = doc.modelspace()
    for e in msp:
        ent = _ezdxf_to_entity(e)
        if ent: nd.entities.append(ent)
        else:   nd.raw_unknown.append({"dxftype": e.dxftype(), "handle": e.dxf.handle})

    # Walk INSERT references — recurse into blocks and capture attributes (TAG = VALUE)
    for ins in msp.query("INSERT"):
        attribs = {a.dxf.tag: a.dxf.text for a in ins.attribs}
        nd.entities.append(Entity(
            kind="block_ref",
            geom={"insert": tuple(ins.dxf.insert), "rotation": ins.dxf.rotation,
                  "xscale": ins.dxf.xscale, "yscale": ins.dxf.yscale},
            layer=ins.dxf.layer,
            block=ins.dxf.name,
            attributes=attribs,
            provenance={"handle": ins.dxf.handle},
        ))


def _ezdxf_to_entity(e) -> Optional[Entity]:
    t = e.dxftype()
    try:
        if t == "LINE":
            s, ee = e.dxf.start, e.dxf.end
            return Entity("line", {"start": tuple(s), "end": tuple(ee)}, e.dxf.layer)
        if t == "LWPOLYLINE":
            pts = [tuple(p) for p in e.get_points("xy")]
            return Entity("polyline", {"points": pts, "closed": e.closed}, e.dxf.layer)
        if t == "POLYLINE":
            pts = [tuple(v.dxf.location) for v in e.vertices]
            return Entity("polyline", {"points": pts}, e.dxf.layer)
        if t == "CIRCLE":
            return Entity("circle", {"center": tuple(e.dxf.center), "radius": e.dxf.radius}, e.dxf.layer)
        if t == "ARC":
            return Entity("arc", {"center": tuple(e.dxf.center), "radius": e.dxf.radius,
                                  "start_angle": e.dxf.start_angle, "end_angle": e.dxf.end_angle}, e.dxf.layer)
        if t in ("TEXT","MTEXT"):
            txt = e.plain_text() if t == "MTEXT" else e.dxf.text
            return Entity("text", {"insert": tuple(e.dxf.insert) if hasattr(e.dxf,"insert") else (0,0,0)},
                          e.dxf.layer, text=txt)
        if t == "HATCH":
            return Entity("hatch", {"pattern": e.dxf.pattern_name}, e.dxf.layer)
    except Exception as ex:
        log.warning("DXF entity decode error %s: %s", t, ex)
    return None


# ──────────────────────────────────────────────────────────────────────────
# DWG — convert to DXF via ODA File Converter, then reuse DXF path
# ──────────────────────────────────────────────────────────────────────────
def _ingest_dwg(path: str, nd: NormalizedDrawing) -> None:
    import shutil, subprocess, tempfile
    oda = shutil.which("ODAFileConverter") or shutil.which("oda_file_converter")
    if not oda:
        raise RuntimeError(
            "DWG ingest requires ODA File Converter on PATH. "
            "Install free from https://www.opendesign.com/guestfiles/oda_file_converter or use libredwg."
        )
    with tempfile.TemporaryDirectory() as out:
        src = tempfile.mkdtemp()
        shutil.copy(path, src)
        subprocess.run([oda, src, out, "ACAD2018", "DXF", "0", "1"], check=True)
        dxf = next(Path(out).glob("*.dxf"))
        _ingest_dxf(str(dxf), nd)
    nd.file_type = "dwg"


# ──────────────────────────────────────────────────────────────────────────
# PDF — extract vector ops AND rasterize pages for image-based analysis
# ──────────────────────────────────────────────────────────────────────────
def _ingest_pdf(path: str, nd: NormalizedDrawing) -> None:
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    nd.page_count = doc.page_count
    nd.metadata.update(doc.metadata or {})
    for pno, page in enumerate(doc):
        # 1) Vector primitives (lines / rects / curves)
        for d in page.get_drawings():
            for item in d["items"]:
                op = item[0]
                if op == "l":
                    nd.entities.append(Entity("line",
                        {"start": tuple(item[1]), "end": tuple(item[2])},
                        layer=f"pdf_p{pno}", page=pno))
                elif op == "re":
                    r = item[1]
                    nd.entities.append(Entity("polyline",
                        {"points": [(r.x0,r.y0),(r.x1,r.y0),(r.x1,r.y1),(r.x0,r.y1)], "closed": True},
                        layer=f"pdf_p{pno}", page=pno))
                elif op == "c":
                    nd.entities.append(Entity("bezier",
                        {"p1": tuple(item[1]),"p2": tuple(item[2]),
                         "p3": tuple(item[3]),"p4": tuple(item[4])},
                        layer=f"pdf_p{pno}", page=pno))
        # 2) Text blocks (already digital, no OCR needed)
        for b in page.get_text("dict")["blocks"]:
            if b.get("type",0) != 0: continue
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    nd.entities.append(Entity("text",
                        {"insert": (sp["bbox"][0], sp["bbox"][1])},
                        layer=f"pdf_p{pno}_text", page=pno, text=sp["text"],
                        attributes={"font": sp.get("font"), "size": sp.get("size")}))
        # 3) Rasterize for symbol/image analysis later
        pix = page.get_pixmap(dpi=200)
        raster_path = f"{path}.p{pno}.png"
        pix.save(raster_path)
        nd.raw_unknown.append({"raster_page": pno, "image": raster_path,
                               "width": pix.width, "height": pix.height})


# ──────────────────────────────────────────────────────────────────────────
# IFC — BIM model (rooms, walls, MEP elements with semantics built-in)
# ──────────────────────────────────────────────────────────────────────────
def _ingest_ifc(path: str, nd: NormalizedDrawing) -> None:
    try:
        import ifcopenshell
    except ImportError:
        raise RuntimeError("IFC ingest requires ifcopenshell. pip install ifcopenshell")
    m = ifcopenshell.open(path)
    nd.metadata["schema"] = m.schema
    # Pull every product (walls, doors, equipment, MEP, sensors, cameras…)
    for prod in m.by_type("IfcProduct"):
        try:
            pset = {}
            for rel in getattr(prod, "IsDefinedBy", []) or []:
                if rel.is_a("IfcRelDefinesByProperties"):
                    pdef = rel.RelatingPropertyDefinition
                    if pdef.is_a("IfcPropertySet"):
                        for p in pdef.HasProperties:
                            if hasattr(p,"NominalValue") and p.NominalValue:
                                pset[p.Name] = p.NominalValue.wrappedValue
            nd.entities.append(Entity(
                kind=prod.is_a().lower(),
                geom={"global_id": prod.GlobalId},
                layer=prod.is_a(),
                attributes={"name": prod.Name, "long_name": getattr(prod,"LongName",None), **pset},
                provenance={"ifc_id": prod.id()},
            ))
        except Exception as ex:
            log.warning("IFC product decode error: %s", ex)


# ──────────────────────────────────────────────────────────────────────────
# Raw image — defer all heavy work to vectorize.py + ocr.py
# ──────────────────────────────────────────────────────────────────────────
def _ingest_image(path: str, nd: NormalizedDrawing) -> None:
    import cv2
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"Cannot read image {path}")
    h, w = img.shape[:2]
    nd.metadata.update({"width": w, "height": h, "channels": img.shape[2] if img.ndim==3 else 1})
    nd.raw_unknown.append({"raster_page": 0, "image": path, "width": w, "height": h})
