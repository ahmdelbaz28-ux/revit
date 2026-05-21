#!/usr/bin/env python3
"""
FireAI V8 Code Review Report Generator
Generates a comprehensive PDF code review report
"""

import os
import sys

# PDF Skill setup
PDF_SKILL_DIR = "/home/z/my-project/skills/pdf"
_scripts = os.path.join(PDF_SKILL_DIR, "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, ListFlowable, ListItem
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

# ── Font Registration ──
FONT_DIR_AR = "/usr/share/fonts/truetype/noto-serif-sc"
FONT_DIR_AR2 = "/usr/share/fonts/truetype/lxgw-wenkai"
FONT_DIR_EN = "/usr/share/fonts/truetype/english"
FONT_DIR_DEJAVU = "/usr/share/fonts/truetype/dejavu"

# Register Arabic/English fonts
try:
    pdfmetrics.registerFont(TTFont('NotoSerifSC', os.path.join(FONT_DIR_AR, 'NotoSerifSC-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('NotoSerifSC-Bold', os.path.join(FONT_DIR_AR, 'NotoSerifSC-Bold.ttf')))
    addMapping('NotoSerifSC', 0, 0, 'NotoSerifSC')
    addMapping('NotoSerifSC', 1, 0, 'NotoSerifSC-Bold')
    BODY_FONT = 'NotoSerifSC'
    HEADING_FONT = 'NotoSerifSC-Bold'
except:
    try:
        pdfmetrics.registerFont(TTFont('Tinos', os.path.join(FONT_DIR_EN, 'Tinos-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Tinos-Bold', os.path.join(FONT_DIR_EN, 'Tinos-Bold.ttf')))
        BODY_FONT = 'Tinos'
        HEADING_FONT = 'Tinos-Bold'
    except:
        BODY_FONT = 'Helvetica'
        HEADING_FONT = 'Helvetica-Bold'

# ── Colors ──
C_PRIMARY = HexColor('#1e3a5f')
C_SECONDARY = HexColor('#2d5a87')
C_ACCENT = HexColor('#c0392b')
C_CRITICAL = HexColor('#e74c3c')
C_WARNING = HexColor('#f39c12')
C_GOOD = HexColor('#27ae60')
C_INFO = HexColor('#2980b9')
C_BG_LIGHT = HexColor('#f0f4f8')
C_TEXT = HexColor('#2c3e50')
C_MUTED = HexColor('#7f8c8d')
C_BORDER = HexColor('#bdc3c7')

# ── Page Setup ──
PAGE_W, PAGE_H = A4
LEFT_M = 20*mm
RIGHT_M = 20*mm
TOP_M = 20*mm
BOTTOM_M = 20*mm
CONTENT_W = PAGE_W - LEFT_M - RIGHT_M

# ── Styles ──
styles = getSampleStyleSheet()

style_title = ParagraphStyle(
    'CustomTitle', parent=styles['Title'],
    fontName=HEADING_FONT, fontSize=24, leading=30,
    textColor=C_PRIMARY, alignment=TA_CENTER, spaceAfter=6*mm
)

style_h1 = ParagraphStyle(
    'CustomH1', parent=styles['Heading1'],
    fontName=HEADING_FONT, fontSize=16, leading=22,
    textColor=C_PRIMARY, spaceBefore=8*mm, spaceAfter=4*mm,
    borderPadding=(3, 0, 3, 0),
    borderWidth=0, borderColor=C_PRIMARY,
)

style_h2 = ParagraphStyle(
    'CustomH2', parent=styles['Heading2'],
    fontName=HEADING_FONT, fontSize=13, leading=18,
    textColor=C_SECONDARY, spaceBefore=5*mm, spaceAfter=3*mm,
)

style_h3 = ParagraphStyle(
    'CustomH3', parent=styles['Heading3'],
    fontName=HEADING_FONT, fontSize=11, leading=16,
    textColor=C_TEXT, spaceBefore=4*mm, spaceAfter=2*mm,
)

style_body = ParagraphStyle(
    'CustomBody', parent=styles['Normal'],
    fontName=BODY_FONT, fontSize=10, leading=16,
    textColor=C_TEXT, alignment=TA_JUSTIFY,
    spaceBefore=1.5*mm, spaceAfter=1.5*mm,
)

style_code = ParagraphStyle(
    'CustomCode', parent=styles['Code'],
    fontName='Courier', fontSize=8.5, leading=12,
    textColor=HexColor('#d35400'), backColor=HexColor('#f8f9fa'),
    borderWidth=0.5, borderColor=C_BORDER, borderPadding=4,
    spaceBefore=2*mm, spaceAfter=2*mm,
    leftIndent=8, rightIndent=8,
)

style_bullet = ParagraphStyle(
    'CustomBullet', parent=style_body,
    leftIndent=15, bulletIndent=5,
    spaceBefore=1*mm, spaceAfter=1*mm,
)

style_crit = ParagraphStyle(
    'Critical', parent=style_body,
    textColor=C_CRITICAL, fontName=HEADING_FONT,
    fontSize=10, leading=15,
)

style_good = ParagraphStyle(
    'Good', parent=style_body,
    textColor=C_GOOD, fontName=HEADING_FONT,
    fontSize=10, leading=15,
)

# ── Helper Functions ──

def heading1(text):
    return Paragraph(text, style_h1)

def heading2(text):
    return Paragraph(text, style_h2)

def heading3(text):
    return Paragraph(text, style_h3)

def body(text):
    return Paragraph(text, style_body)

def code(text):
    return Paragraph(text.replace('<', '&lt;').replace('>', '&gt;'), style_code)

def bullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", style_bullet)

def critical(text):
    return Paragraph(f"<font color='#e74c3c'>&#9888;</font> {text}", style_crit)

def good(text):
    return Paragraph(f"<font color='#27ae60'>&#10003;</font> {text}", style_good)

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=3*mm, spaceBefore=3*mm)

def spacer(h=3*mm):
    return Spacer(1, h)

def severity_badge(level):
    colors = {
        'CRITICAL': C_CRITICAL,
        'HIGH': HexColor('#e67e22'),
        'MEDIUM': C_WARNING,
        'LOW': C_INFO,
    }
    c = colors.get(level, C_MUTED)
    return f"<font color='{c.hexval()}'><b>[{level}]</b></font>"

def make_table(headers, rows, col_widths=None):
    """Create a styled table."""
    data = [headers] + rows
    if col_widths is None:
        col_widths = [CONTENT_W / len(headers)] * len(headers)
    
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('FONTNAME', (0, 0), (-1, 0), HEADING_FONT),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), BODY_FONT),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('LEADING', (0, 0), (-1, -1), 13),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), C_BG_LIGHT]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


# ════════════════════════════════════════════════════════════
# BUILD THE DOCUMENT
# ════════════════════════════════════════════════════════════

output_path = "/home/z/my-project/download/FireAI_V8_Code_Review_Report.pdf"

doc = SimpleDocTemplate(
    output_path,
    pagesize=A4,
    leftMargin=LEFT_M, rightMargin=RIGHT_M,
    topMargin=TOP_M, bottomMargin=BOTTOM_M,
    title="FireAI V8 Code Review Report",
    author="Z.ai Code Reviewer",
    subject="Comprehensive Code Review and Critique"
)

story = []

# ── COVER / TITLE ──
story.append(Spacer(1, 30*mm))
story.append(Paragraph("FireAI V8.0", ParagraphStyle(
    'CoverTitle', fontName=HEADING_FONT, fontSize=32, leading=40,
    textColor=C_PRIMARY, alignment=TA_CENTER
)))
story.append(Spacer(1, 5*mm))
story.append(Paragraph("Comprehensive Code Review Report", ParagraphStyle(
    'CoverSub', fontName=BODY_FONT, fontSize=16, leading=22,
    textColor=C_SECONDARY, alignment=TA_CENTER
)))
story.append(Spacer(1, 8*mm))
story.append(HRFlowable(width="60%", thickness=2, color=C_PRIMARY, spaceAfter=5*mm, spaceBefore=5*mm))
story.append(Spacer(1, 5*mm))
story.append(Paragraph("Critical Analysis &amp; Improvement Recommendations", ParagraphStyle(
    'CoverDesc', fontName=BODY_FONT, fontSize=11, leading=16,
    textColor=C_MUTED, alignment=TA_CENTER
)))
story.append(Spacer(1, 15*mm))

# Summary box
summary_data = [
    ['Metric', 'Value'],
    ['Project', 'FireAI V8.0 - Multi-Layer Fire Alarm Design Engine'],
    ['Files Reviewed', '25+ core files across 8 modules'],
    ['Critical Issues', '8'],
    ['High Issues', '10'],
    ['Medium Issues', '7'],
    ['Strengths Identified', '12'],
    ['Recommendations', '22'],
    ['Overall Rating', 'B- (Good foundation, significant refactoring needed)'],
]
summary_table = Table(summary_data, colWidths=[CONTENT_W*0.35, CONTENT_W*0.65])
summary_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
    ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
    ('FONTNAME', (0, 0), (-1, 0), HEADING_FONT),
    ('FONTNAME', (0, 1), (-1, -1), BODY_FONT),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('LEADING', (0, 0), (-1, -1), 14),
    ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), C_BG_LIGHT]),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ('LEFTPADDING', (0, 0), (-1, -1), 8),
]))
story.append(summary_table)
story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# SECTION 1: EXECUTIVE SUMMARY
# ════════════════════════════════════════════════════════════
story.append(heading1("1. Executive Summary"))
story.append(body(
    "FireAI V8.0 is an ambitious, multi-layer fire alarm design engine that automates compliance checking "
    "and device placement according to NFPA 72 and BS 5839 standards. The project demonstrates strong engineering "
    "intent with safety-first design philosophy, triple-check verification gates, and tamper-proof audit trails. "
    "However, the codebase suffers from significant architectural debt: duplicate model definitions scattered "
    "across multiple files, inconsistent constants that threaten safety-critical calculations, deprecated modules "
    "still in the production path, and a general lack of type safety and dependency injection. This review "
    "identifies 25 issues across critical, high, and medium severity levels, alongside 12 notable strengths "
    "that should be preserved and amplified in any refactoring effort."
))
story.append(body(
    "The most dangerous finding is the <b>inconsistent NFPA 72 spacing constants</b> across the codebase: "
    "9.1m in safety_gates.py vs. 9.2m default in code_compliance_engine.py vs. 6.77m vs. 6.1m for heat "
    "detectors. In a life-safety system, a 0.1m discrepancy can mean the difference between code compliance "
    "and a failed inspection. The second critical finding is the <b>duplicate Violation class</b> defined in "
    "three separate files with different field sets, which creates a maintenance nightmare where fixing a bug "
    "in one location silently leaves it present in others."
))

story.append(spacer(5*mm))

# Rating table
rating_data = [
    ['Category', 'Rating', 'Notes'],
    ['Safety Correctness', 'B', 'NFPA 72 core logic is sound after V7.3 fix; constant inconsistencies are concerning'],
    ['Architecture', 'C+', 'Good intent with Clean Architecture; poor execution with duplicate models everywhere'],
    ['Code Quality', 'C', 'Mixed languages, bare excepts, print() instead of logging, no type hints on key interfaces'],
    ['Security', 'B-', 'Good encryption/token design; sys.path manipulation and global mutable state are risks'],
    ['Test Coverage', 'C+', 'Many test files exist but with unprofessional names; no clear coverage metrics'],
    ['Maintainability', 'D+', 'Severe DRY violations; deprecated modules in production path; no dependency injection'],
]
story.append(make_table(
    [Paragraph(h, style_body) for h in rating_data[0]],
    [[Paragraph(c, style_body) for c in row] for row in rating_data[1:]],
    col_widths=[CONTENT_W*0.25, CONTENT_W*0.12, CONTENT_W*0.63]
))

# ════════════════════════════════════════════════════════════
# SECTION 2: CRITICAL ISSUES
# ════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(heading1("2. Critical Issues (Must Fix)"))

# Issue 2.1
story.append(heading2("2.1 Inconsistent NFPA 72 Spacing Constants"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Life-Safety Impact", style_crit))
story.append(body(
    "The NFPA 72 spacing constants are defined independently in multiple files with conflicting values. "
    "This is the single most dangerous issue in the codebase because fire alarm spacing directly determines "
    "whether a building's occupants will receive timely warning of a fire. The discrepancies are as follows:"
))

const_data = [
    ['Constant', 'safety_gates.py', 'code_compliance_engine.py', 'production_config.py', 'Correct Value'],
    ['Smoke Spacing', '9.1m', '9.2m (default)', '9.1m', '9.1m (30ft)'],
    ['Heat Spacing', '6.1m', 'N/A', '6.77m', '6.1m (20ft)'],
    ['Coverage Factor', 'N/A', 'N/A', '0.7', '0.7'],
    ['Wall Distance', '4.55m', 'N/A', 'N/A', '4.55m (S/2)'],
]
story.append(make_table(
    [Paragraph(h, style_body) for h in const_data[0]],
    [[Paragraph(c, style_body) for c in row] for row in const_data[1:]],
    col_widths=[CONTENT_W*0.18, CONTENT_W*0.18, CONTENT_W*0.22, CONTENT_W*0.22, CONTENT_W*0.20]
))
story.append(spacer(3*mm))
story.append(body(
    "<b>Root Cause:</b> Each module independently defines its own constants instead of importing from "
    "the centralized ProductionConfig. The production_config.py file exists and is well-structured, but "
    "it is not the single source of truth in practice."
))
story.append(body(
    "<b>Recommendation:</b> Immediately refactor all modules to import NFPA constants exclusively from "
    "ProductionConfig. Add a startup validation check that compares all constants against a reference "
    "table and fails fast if any mismatch is detected. Add a unit test that asserts all constant values "
    "match the NFPA 72-2022 specification exactly."
))

# Issue 2.2
story.append(heading2("2.2 Duplicate Violation Class (3 Definitions)"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Maintenance &amp; Safety", style_crit))
story.append(body(
    "The Violation dataclass is defined in three separate files with different field sets. This violates "
    "the DRY principle at its most dangerous level: a bug fix in one definition will silently remain in "
    "the others, and the different field sets mean code expecting one definition will crash or produce "
    "incorrect results when receiving another."
))

viol_data = [
    ['File', 'Fields', 'Differences'],
    ['core/models.py', 'rule, device_id, location, value, threshold', 'Base definition - 5 fields'],
    ['code_compliance_engine.py', 'location, description, code_reference, severity, min_required, actual_distance', 'Completely different! 6 fields, only location overlaps'],
    ['spatial_field_engine.py', 'rule, device_id, severity, message, value, threshold, location', 'Has message field (forbidden by contract.py)'],
]
story.append(make_table(
    [Paragraph(h, style_body) for h in viol_data[0]],
    [[Paragraph(c, style_body) for c in row] for row in viol_data[1:]],
    col_widths=[CONTENT_W*0.25, CONTENT_W*0.40, CONTENT_W*0.35]
))
story.append(spacer(3*mm))
story.append(body(
    "<b>Critical Conflict:</b> The contract.py module explicitly forbids the 'message' field in Violation "
    "objects, yet spatial_field_engine.py defines Violation with a 'message' field. This means the "
    "ComplianceOracle must sanitize every violation it receives, which is a fragile workaround rather than "
    "a proper solution."
))
story.append(body(
    "<b>Recommendation:</b> Define a single canonical Violation class in core/models.py with all necessary "
    "fields. All other modules must import from this single source. Add a type alias if different names "
    "are needed for clarity."
))

# Issue 2.3
story.append(heading2("2.3 Duplicate Conflict Class (2 Definitions)"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Code Duplication", style_crit))
story.append(body(
    "The Conflict dataclass is defined identically in both core/models.py and core/conflict_resolver.py. "
    "This is a textbook DRY violation. If a field is added or modified in one, the other will diverge "
    "silently. The ConflictResolver class in conflict_resolver.py should import Conflict from models.py."
))
story.append(body(
    "<b>Recommendation:</b> Delete the Conflict definition from conflict_resolver.py and import it from "
    "core/models.py. Run all tests to verify no behavioral change."
))

# Issue 2.4
story.append(heading2("2.4 content_hash Uses Non-Deterministic Python hash()"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Security &amp; Audit", style_crit))
story.append(body(
    "In core/models.py, the UniversalElement.add_change_log_entry() method computes content_hash as: "
))
story.append(code("self.content_hash = str(hash(str(self.to_dict())))"))
story.append(body(
    "Python's built-in hash() is non-deterministic across sessions (PYTHONHASHSEED randomization). "
    "This means the same element can have different content_hash values in different runs, completely "
    "defeating the purpose of content hashing for audit integrity. In a life-safety system where audit "
    "trails must be tamper-proof and reproducible, this is unacceptable."
))
story.append(body(
    "<b>Recommendation:</b> Replace with SHA-256: "
))
story.append(code("self.content_hash = hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()"))

# Issue 2.5
story.append(heading2("2.5 NEC MAX_CONDUCTOR_FILL Dict Has Duplicate Key"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Data Integrity", style_crit))
story.append(body(
    "In core/code_compliance_engine.py, the NECCompliance.MAX_CONDUCTOR_FILL dictionary has the key "
    "'40%' defined twice (lines 303-307). In Python, the second definition silently overwrites the first, "
    "meaning the '31%' entry is lost. The correct dictionary should be: "
))
story.append(code('{"1_wire": 0.53, "2_wires": 0.31, "3_plus": 0.40}'))
story.append(body(
    "This means any code calling nec_conduit_fill('2_wires') would get 0.40 instead of the correct 0.31, "
    "potentially allowing conduit overfill - a fire hazard in electrical installations."
))

# Issue 2.6
story.append(heading2("2.6 Database Connections Without Context Managers"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Reliability", style_crit))
story.append(body(
    "In core/database.py, the _persist_element() and load_from_database() methods use sqlite3.connect() "
    "without context managers (with statements). If an exception occurs between connect() and close(), "
    "the connection leaks. This can exhaust the connection pool under load, causing the application to "
    "hang or crash. In a production system processing building safety data, a connection leak during a "
    "critical write could mean lost audit records."
))
story.append(body(
    "<b>Recommendation:</b> Replace all bare connect/close pairs with 'with sqlite3.connect() as conn:' "
    "context managers. Better yet, use a connection pool with proper lifecycle management."
))

# Issue 2.7
story.append(heading2("2.7 ComplianceOracle Audit File Lifecycle Mismanagement"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Resource Leak", style_crit))
story.append(body(
    "The ComplianceOracle.__init__() opens a file in append mode and relies on __del__() to close it. "
    "Python's __del__() is not guaranteed to be called, especially in long-running processes or during "
    "abnormal shutdown. This creates both a resource leak and a risk of data loss if the buffer is not "
    "flushed before the process terminates."
))
story.append(body(
    "<b>Recommendation:</b> Implement the context manager protocol (__enter__/__exit__) and use the "
    "oracle with a 'with' statement. Alternatively, flush after every write (which it currently does) "
    "and add atexit registration for cleanup."
))

# Issue 2.8
story.append(heading2("2.8 sys.path Manipulation at Module Level"))
story.append(Paragraph(f"{severity_badge('CRITICAL')} Security", style_crit))
story.append(body(
    "Both validation/compliance_oracle.py and core/truth_deriver.py insert directories into sys.path "
    "at module import time using sys.path.insert(0, ...). This is a well-known security anti-pattern "
    "because it allows shadow imports - a malicious package placed in the inserted directory could "
    "replace any standard library or project module. In a safety-critical system, this is especially "
    "dangerous because a compromised import could silently alter NFPA compliance calculations."
))
story.append(body(
    "<b>Recommendation:</b> Fix the package structure so all imports work without sys.path manipulation. "
    "Use proper __init__.py files and relative imports. If absolute paths are needed, use a proper "
    "package installation (pip install -e .)."
))

# ════════════════════════════════════════════════════════════
# SECTION 3: HIGH SEVERITY ISSUES
# ════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(heading1("3. High Severity Issues"))

# 3.1
story.append(heading2("3.1 Deprecated Module in Production Path"))
story.append(Paragraph(f"{severity_badge('HIGH')} Architecture", style_crit))
story.append(body(
    "spatial_field_engine.py is explicitly marked as DEPRECATED in its docstring, yet it is imported "
    "by validation/compliance_oracle.py which is the core production verification pipeline. The deprecation "
    "notice points to fireai.core.nfpa72_models/nfpa72_calculations/nfpa72_coverage as the canonical "
    "implementations, but the migration has not been completed. This creates a situation where bug fixes "
    "may be applied to the canonical modules but not to the deprecated one still in the critical path."
))

# 3.2
story.append(heading2("3.2 Truth Deriver Claims Independence But Has Circular Dependency"))
story.append(Paragraph(f"{severity_badge('HIGH')} Reliability", style_crit))
story.append(body(
    "core/truth_deriver.py states in its docstring: 'NO imports from spatial_field_engine, evaluate_compliance, "
    "or SpatialValidator.' However, its self-test function (_run_self_test, line 259) imports from "
    "spatial_field_engine. While the production code path may be independent, the test creates a coupling "
    "that can mask bugs if the two modules diverge. The truth deriver should have completely independent "
    "tests that do not import from the engine it is supposed to verify."
))

# 3.3
story.append(heading2("3.3 Global Mutable Singleton GLOBAL_MEMORY"))
story.append(Paragraph(f"{severity_badge('HIGH')} Thread Safety", style_crit))
story.append(body(
    "In core/cognitive_core.py, a global CognitiveMemoryBank instance is created at module import time "
    "(line 140: GLOBAL_MEMORY = CognitiveMemoryBank()). This singleton uses a plain dict for its "
    "knowledge_graph with no thread safety mechanisms. In a multi-threaded web server processing "
    "concurrent requests, simultaneous modifications to this dict could corrupt the knowledge base "
    "or cause KeyError exceptions during iteration."
))
story.append(body(
    "<b>Recommendation:</b> Either use threading.Lock() to protect all accesses, or better yet, use "
    "dependency injection to pass the memory bank as a parameter rather than using a global singleton."
))

# 3.4
story.append(heading2("3.4 Heat Detector Coverage Uses Wrong Geometry Model"))
story.append(Paragraph(f"{severity_badge('HIGH')} Safety Correctness", style_crit))
story.append(body(
    "The spatial_field_engine.py applies the 0.7 coverage factor uniformly to all detector types, "
    "computing max_allowed_distance as coverage_factor * rated_spacing. For heat detectors, this gives "
    "0.7 * 6.1 = 4.27m as a circular (Euclidean) radius. However, NFPA 72 specifies heat detector "
    "coverage using square (Chebyshev) geometry, not circular. Using a circular model for heat detectors "
    "underestimates the actual coverage area, potentially leading to over-specification. The deprecation "
    "notice acknowledges this but the module remains in production."
))

# 3.5
story.append(heading2("3.5 Truth Deriver NFPAConstraintModel Uses Different Formula"))
story.append(Paragraph(f"{severity_badge('HIGH')} Consistency", style_crit))
story.append(body(
    "The NFPAConstraintModel in truth_deriver.py returns rated_spacing directly as max_allowed_distance "
    "(line 85: return self.rated_spacing.get(device_type, 9.1)), while the same class in "
    "spatial_field_engine.py applies a coverage_factor (0.7) to compute max_allowed_distance. This means "
    "the two independent verification paths use different thresholds for the same check - the truth deriver "
    "is more lenient (9.1m for smoke) while the engine is stricter (6.37m for smoke). This discrepancy "
    "can cause the cross-verification in ComplianceOracle to produce misleading results."
))

# 3.6
story.append(heading2("3.6 No Thread Safety on UniversalDataModel"))
story.append(Paragraph(f"{severity_badge('HIGH')} Concurrency", style_crit))
story.append(body(
    "The UniversalDataModel class in core/database.py uses plain Python dicts (self.elements, "
    "self.relationships, self.conflicts) with no synchronization. Multiple concurrent update_element() "
    "calls could interleave, causing data corruption or lost updates. The database writes are also "
    "not atomic - a crash between the in-memory update and the SQLite persist could leave the two "
    "out of sync."
))

# 3.7
story.append(heading2("3.7 Bare Except Clause in DXF Parser"))
story.append(Paragraph(f"{severity_badge('HIGH')} Code Quality", style_crit))
story.append(body(
    "In parsers/dxf_parser.py, line 188 contains a bare 'except:' clause that catches all exceptions "
    "including SystemExit and KeyboardInterrupt. This can mask critical errors during file parsing, "
    "such as out-of-memory conditions or corruption. It should be replaced with 'except Exception:' "
    "at minimum, or better yet, specific exception types."
))

# 3.8
story.append(heading2("3.8 print() Instead of Logging in Security Modules"))
story.append(Paragraph(f"{severity_badge('HIGH')} Security", style_crit))
story.append(body(
    "The encryption.py module uses print() for error messages (lines 143 and 197: "
    "'print(f\"[!] Audit log failed: {e}\")'). In a production system, print() output goes to stdout "
    "which may not be captured by log aggregation systems, may be visible to unauthorized users, and "
    "cannot be filtered by severity. Security-related errors should always use proper logging with "
    "appropriate severity levels."
))

# 3.9
story.append(heading2("3.9 semantic_checksum Omits Severity Field"))
story.append(Paragraph(f"{severity_badge('HIGH')} Audit Integrity", style_crit))
story.append(body(
    "In validation/compliance_oracle.py, the _semantic_checksum function computes SHA-256 over "
    "(rule, device_id, quantized_location, value, threshold) but excludes the 'severity' field. "
    "This means two violations with identical rule/device_id/value/threshold but different severities "
    "(e.g., CRITICAL vs. INFO) would produce the same checksum. In an audit context, this means a "
    "severity downgrade attack would not be detected by checksum verification."
))

# 3.10
story.append(heading2("3.10 Duplicate Import of datetime in ComplianceOracle"))
story.append(Paragraph(f"{severity_badge('HIGH')} Code Quality", style_crit))
story.append(body(
    "In validation/compliance_oracle.py, 'from datetime import datetime' appears on both line 28 and "
    "line 39. While functionally harmless, it indicates careless code organization and suggests the "
    "file may have been assembled from multiple sources without proper review."
))

# ════════════════════════════════════════════════════════════
# SECTION 4: MEDIUM SEVERITY ISSUES
# ════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(heading1("4. Medium Severity Issues"))

# 4.1
story.append(heading2("4.1 Ray Casting with Epsilon Hack"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Correctness", style_body))
story.append(body(
    "In core/geometry_kernel.py, the _ray_cast method uses '(yj - yi + 1e-30)' to avoid division by zero. "
    "While this works in practice, it introduces a small numerical bias that could cause incorrect results "
    "for points exactly on polygon edges. A more robust approach would use the winding number algorithm "
    "or handle the degenerate case explicitly."
))

# 4.2
story.append(heading2("4.2 No Type Hints on Critical Interface Parameters"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Maintainability", style_body))
story.append(body(
    "The db_pool parameter in encryption.py (EncryptedAuditLog and SecureOverrideConsumer) and the "
    "ceiling_info parameter in code_compliance_engine.py have no type annotations. The code uses "
    "hasattr() to check for attributes, which is fragile and defeats the purpose of type checking. "
    "Define proper Protocol or ABC classes for these interfaces."
))

# 4.3
story.append(heading2("4.3 DXF Spline Parsing May Crash on Non-Standard Files"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Reliability", style_body))
story.append(body(
    "The _spline_to_segments method in dxf_parser.py accesses 'p.dxf.location.x' for control points, "
    "which may not exist for all SPLINE entity types (e.g., rational B-splines use fit points instead "
    "of control points). This could raise AttributeError on non-standard DXF files."
))

# 4.4
story.append(heading2("4.4 No Database Connection Pooling"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Performance", style_body))
story.append(body(
    "The UniversalDataModel._persist_element() creates a new SQLite connection for every write operation. "
    "Under high write throughput, this creates significant overhead. A connection pool with prepared "
    "statements would improve performance by 10-100x for batch operations."
))

# 4.5
story.append(heading2("4.5 Test Files with Dramatic/Unprofessional Names"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Professionalism", style_body))
story.append(body(
    "The test directory contains files named test_apocalypse_protocol.py, test_omega_protocol.py, "
    "test_hell_protocol_week2.py, test_singularity_protocol.py, test_deadlock_doom_protocol.py, "
    "test_physical_suicide_protocol.py, and others with similarly dramatic names. While creative, "
    "these names make it extremely difficult for new team members to understand what each test "
    "actually covers. Tests should have descriptive names that indicate the functionality being tested."
))

# 4.6
story.append(heading2("4.6 Mixed Arabic/English Comments Without Consistency"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Code Quality", style_body))
story.append(body(
    "The codebase mixes Arabic and English comments extensively. While bilingual documentation is "
    "valuable, the current approach is inconsistent - some files use Arabic for docstrings and English "
    "for inline comments, others do the reverse. This makes the code harder to maintain for a diverse "
    "team. Adopt a consistent policy: English for code identifiers and inline comments, Arabic for "
    "user-facing documentation only."
))

# 4.7
story.append(heading2("4.7 No Dependency Injection - Hard-Coded Imports"))
story.append(Paragraph(f"{severity_badge('MEDIUM')} Testability", style_body))
story.append(body(
    "Most classes create their dependencies internally (e.g., ComplianceOracle creates SpatialNormalizer "
    "and NFPAConstraintModel inside __init__). This makes unit testing difficult because there is no "
    "way to inject mock objects. For example, testing ComplianceOracle with a specific set of violations "
    "requires the entire engine pipeline to be set up correctly. Use constructor injection for all "
    "external dependencies."
))

# ════════════════════════════════════════════════════════════
# SECTION 5: STRENGTHS
# ════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(heading1("5. Notable Strengths (Must Preserve)"))

story.append(heading2("5.1 Safety-First Design Philosophy"))
story.append(good(
    "The entire codebase demonstrates an exceptional commitment to safety. The Triple-Check Gate "
    "(proof_valid AND nfpa_valid AND NOT fallback_used), the fail-closed approach in DXF parsing, "
    "the explicit CRITICAL FIX documentation in README.md, and the safety warning that the tool is "
    "an assistant, not a replacement for engineer judgment - all show mature safety awareness."
))

story.append(heading2("5.2 Tamper-Proof Audit Trail"))
story.append(good(
    "The AuditStore with SHA-256 hash chain and HMAC-SHA256 signatures is well-implemented. SQL triggers "
    "that prevent UPDATE and DELETE operations on audit records, combined with the verify_chain() method "
    "that detects tampering, provide strong integrity guarantees. This is exactly what a safety-critical "
    "system needs."
))

story.append(heading2("5.3 ProductionConfig as Centralized Constants"))
story.append(good(
    "The ProductionConfig class in core/production_config.py is well-designed with dot-notation accessors, "
    "immutability guarantees, override support for testing, and comprehensive NFPA/NEC/routing/IFC constants. "
    "The problem is that other modules don't use it - but the design itself is excellent."
))

story.append(heading2("5.4 Robust Geometry Kernel"))
story.append(good(
    "The Polygon2D class in core/geometry_kernel.py is remarkably well-implemented. Features include: "
    "snap-to-grid deduplication, CCW/CW winding order normalization, self-intersection detection with "
    "Shapely fallback, bounding box caching, ray-casting point-in-polygon with hole support, centroid "
    "calculation, and Shapely conversion with make_valid fallback. This is production-quality code."
))

story.append(heading2("5.5 V7.3 Coverage Fix (R = 0.7 x S)"))
story.append(good(
    "The critical fix from commit 6715c55 that corrected the coverage radius from S/2 (4.55m) to "
    "R = 0.7 x S (6.37m) demonstrates the team's ability to identify and fix fundamental engineering "
    "errors. The thorough documentation of the fix in README.md, including the V7.2 vs V7.3 comparison "
    "and the known failure analysis, is exemplary."
))

story.append(heading2("5.6 DXF Parser with Recovery Mode"))
story.append(good(
    "The DXFParser's approach of trying normal read first, then falling back to ezdxf.recover.readfile() "
    "for corrupted files, combined with unit detection heuristics for INSUNITS=0 files, is robust and "
    "well-thought-out. The safety-first approach of rejecting files with inconclusive unit detection "
    "is exactly right for a safety-critical application."
))

story.append(heading2("5.7 3D Distance Fix in CodeComplianceEngine"))
story.append(good(
    "The V12 fix that added true 3D distance calculation to prevent the '2D Projection Fallacy' is "
    "excellent. The previous code calculated distance in 2D only, causing false violations when a "
    "detector on the ceiling was above a floor-level obstruction. The fix correctly computes 3D Euclidean "
    "distance when height information is available, with a conservative 2D fallback."
))

story.append(heading2("5.8 Secure Token and Encryption Design"))
story.append(good(
    "The encryption.py module uses AES-256 via Fernet, the secure_tokens.py module uses 256-bit entropy "
    "from secrets.token_hex with SHA-256 hash-only storage, and both use constant-time comparison "
    "(secrets.compare_digest) to prevent timing attacks. The key generation uses secrets.token_bytes "
    "instead of subprocess/openssl (VULN-031 fix). This is security best practice."
))

story.append(heading2("5.9 Longest-Match Semantic Recognition"))
story.append(good(
    "The V12 fix in cognitive_core.py that changed the semantic recognition from first-match to "
    "longest-match is a critical safety improvement. The previous 'any(p in layer for p in patterns)' "
    "caused 'F-DET' to match 'F-DET-H', classifying heat detectors as smoke detectors - a "
    "life-safety catastrophe. The longest-match strategy correctly disambiguates these cases."
))

story.append(heading2("5.10 Wall-Hugging Fallacy Fix"))
story.append(good(
    "The EliteDecisionEngine correctly identifies and fixes the 'Wall-Hugging Fallacy' where previous "
    "code suggested moving detectors closer to walls when they were far from them. NFPA 72 does NOT "
    "require detectors to be near walls - it requires adequate area coverage. The fix properly checks "
    "dead air space (minimum 0.1m from wall) and area coverage percentage instead."
))

story.append(heading2("5.11 Duplicate Polygon Detection in DXF Parser"))
story.append(good(
    "The _remove_duplicates() method that detects polygons with >90% overlap and keeps the larger one "
    "is a practical solution to a common problem in CAD file parsing where the same room may be defined "
    "by multiple overlapping entities. The approach is well-implemented with proper edge case handling."
))

story.append(heading2("5.12 Comprehensive Engineering Constants"))
story.append(good(
    "The production_config.py file contains an impressively comprehensive set of engineering constants "
    "spanning NFPA 72 (spacing, sound pressure, monitoring), NEC (conduit fill, wire gauge, derating), "
    "building codes, routing constraints, IFC schema details, and geometry tolerances. The self-test "
    "function validates all values against known references."
))

# ════════════════════════════════════════════════════════════
# SECTION 6: ARCHITECTURAL RECOMMENDATIONS
# ════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(heading1("6. Architectural Recommendations"))

story.append(heading2("6.1 Unify All Models into a Single Module"))
story.append(body(
    "The most impactful refactoring would be to consolidate all data model definitions into a single "
    "authoritative module. Currently, Room, Device, Obstruction, and Violation are defined in "
    "core/models.py, spatial_constraint_engine.py, and spatial_field_engine.py with different field "
    "sets. The unified module should:"
))
story.append(bullet("Define each model exactly once with all necessary fields"))
story.append(bullet("Use Protocol/ABC classes for interface flexibility"))
story.append(bullet("Provide backward-compatible aliases for gradual migration"))
story.append(bullet("Include a migration guide for existing code"))

story.append(heading2("6.2 Complete the ProductionConfig Migration"))
story.append(body(
    "Every module that defines NFPA/NEC constants locally must be refactored to import from "
    "ProductionConfig. Add a deprecation warning system that flags any local constant definitions "
    "that duplicate ProductionConfig values. Create a CI check that fails the build if any local "
    "constants are found."
))

story.append(heading2("6.3 Implement Dependency Injection"))
story.append(body(
    "Replace all hard-coded instantiation with constructor injection. The ComplianceOracle should "
    "receive its SpatialNormalizer, NFPAConstraintModel, and audit file as constructor parameters. "
    "This enables proper unit testing with mocks and makes the codebase more maintainable."
))

story.append(heading2("6.4 Complete the Deprecated Module Migration"))
story.append(body(
    "The spatial_field_engine.py migration to the canonical fireai.core modules must be completed. "
    "This should be tracked as a blocking issue. The migration plan should include: (1) Update "
    "ComplianceOracle to use the canonical modules, (2) Run parallel verification against both "
    "implementations, (3) Remove the deprecated module only after 100% consistency is confirmed."
))

story.append(heading2("6.5 Fix the Truth Deriver Consistency"))
story.append(body(
    "The Truth Deriver's NFPAConstraintModel must use the same coverage_factor calculation as the "
    "engine's model. The whole point of an independent verification is to catch bugs in the engine, "
    "but if the two use different formulas, they will always produce different results for non-trivial "
    "inputs, making the comparison meaningless."
))

story.append(heading2("6.6 Standardize Logging"))
story.append(body(
    "Replace all print() statements with proper logging calls. Define a consistent logging format "
    "that includes timestamp, severity, module name, and correlation ID for tracing requests through "
    "the pipeline. Use structlog (already in requirements.txt) for structured JSON logging in production."
))

story.append(heading2("6.7 Add Runtime Constant Validation"))
story.append(body(
    "Create a startup validation function that compares all NFPA/NEC constants across the codebase "
    "and raises an error if any inconsistencies are detected. This should run as part of the "
    "application initialization and as a CI check. The function should compare values in "
    "ProductionConfig against the NFPA 72-2022 specification reference."
))

# ════════════════════════════════════════════════════════════
# SECTION 7: PRIORITY ACTION PLAN
# ════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(heading1("7. Priority Action Plan"))

priority_data = [
    ['Priority', 'Action', 'Impact', 'Effort'],
    ['P0 (Immediate)', 'Fix NFPA 72 constant inconsistencies', 'Life Safety', '2 hours'],
    ['P0 (Immediate)', 'Fix NEC conductor fill duplicate key', 'Fire Hazard', '5 minutes'],
    ['P0 (Immediate)', 'Replace hash() with SHA-256 in content_hash', 'Audit Integrity', '30 minutes'],
    ['P1 (This Week)', 'Unify Violation class to single definition', 'Safety + Maintenance', '4 hours'],
    ['P1 (This Week)', 'Unify Conflict class to single definition', 'Maintenance', '30 minutes'],
    ['P1 (This Week)', 'Fix sys.path manipulation', 'Security', '2 hours'],
    ['P1 (This Week)', 'Fix ComplianceOracle file lifecycle', 'Resource Leak', '1 hour'],
    ['P1 (This Week)', 'Fix database connection management', 'Reliability', '2 hours'],
    ['P2 (This Sprint)', 'Migrate from spatial_field_engine.py', 'Architecture', '8 hours'],
    ['P2 (This Sprint)', 'Fix Truth Deriver formula consistency', 'Verification', '3 hours'],
    ['P2 (This Sprint)', 'Add dependency injection', 'Testability', '8 hours'],
    ['P2 (This Sprint)', 'Replace print() with logging', 'Security + Ops', '2 hours'],
    ['P3 (Next Sprint)', 'Rename dramatic test files', 'Professionalism', '2 hours'],
    ['P3 (Next Sprint)', 'Standardize comment language policy', 'Code Quality', '4 hours'],
    ['P3 (Next Sprint)', 'Add runtime constant validation', 'Safety Net', '4 hours'],
]
story.append(make_table(
    [Paragraph(h, style_body) for h in priority_data[0]],
    [[Paragraph(c, style_body) for c in row] for row in priority_data[1:]],
    col_widths=[CONTENT_W*0.18, CONTENT_W*0.42, CONTENT_W*0.22, CONTENT_W*0.18]
))

story.append(spacer(8*mm))
story.append(heading1("8. Conclusion"))
story.append(body(
    "FireAI V8.0 is built on a solid engineering foundation with genuinely innovative safety mechanisms "
    "(triple-check gates, tamper-proof audit trails, longest-match semantic recognition). The core "
    "algorithms are mathematically sound after the V7.3 coverage fix. However, the codebase has "
    "accumulated significant technical debt through duplicated model definitions, inconsistent constants, "
    "deprecated modules in production paths, and poor separation of concerns. The most urgent priority "
    "is fixing the NFPA 72 constant inconsistencies, as these directly affect life-safety calculations. "
    "The second priority is unifying the model definitions to eliminate the DRY violations that make "
    "the codebase fragile and dangerous to maintain."
))
story.append(body(
    "With the recommended refactoring, this project could evolve from its current B- rating to a solid A. "
    "The underlying safety philosophy is exemplary - it just needs cleaner execution. The recommended "
    "changes are straightforward and can be implemented incrementally without disrupting the existing "
    "functionality, provided the migration is done with proper testing at each step."
))

# ── BUILD ──
doc.build(story)
print(f"Report generated: {output_path}")
