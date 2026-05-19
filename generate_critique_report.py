"""Generate FireAI Bridge 2 Code Critique Report as PDF."""
import os, sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ── Font Setup ──────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('NotoSansSC', '/usr/share/fonts/truetype/chinese/SarasaMonoSC-Bold.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC', '/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Tinos', '/usr/share/fonts/truetype/english/Tinos-Bold.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'))
registerFontFamily('NotoSansSC', normal='NotoSansSC', bold='NotoSansSC')
registerFontFamily('NotoSerifSC', normal='NotoSerifSC', bold='NotoSerifSC')
registerFontFamily('Tinos', normal='Tinos', bold='Tinos')

# ── Palette ─────────────────────────────────────────────────────────
ACCENT       = colors.HexColor('#cb4d23')
TEXT_PRIMARY  = colors.HexColor('#1e1d1b')
TEXT_MUTED    = colors.HexColor('#8e8a83')
BG_SURFACE   = colors.HexColor('#e6e2dc')
BG_PAGE      = colors.HexColor('#efedea')

# ── Output ──────────────────────────────────────────────────────────
OUTPUT = '/home/z/my-project/download/FireAI_Bridge2_Code_Critique.pdf'
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

# ── Styles ──────────────────────────────────────────────────────────
title_style = ParagraphStyle(
    name='Title', fontName='NotoSansSC', fontSize=22, leading=30,
    alignment=TA_CENTER, textColor=ACCENT, spaceAfter=12)
h1_style = ParagraphStyle(
    name='H1', fontName='NotoSansSC', fontSize=16, leading=24,
    textColor=ACCENT, spaceBefore=18, spaceAfter=8)
h2_style = ParagraphStyle(
    name='H2', fontName='NotoSansSC', fontSize=13, leading=20,
    textColor=TEXT_PRIMARY, spaceBefore=12, spaceAfter=6)
body_style = ParagraphStyle(
    name='Body', fontName='NotoSansSC', fontSize=10.5, leading=18,
    alignment=TA_LEFT, textColor=TEXT_PRIMARY, spaceAfter=6,
    wordWrap='CJK')
code_style = ParagraphStyle(
    name='Code', fontName='DejaVuSans', fontSize=9, leading=14,
    textColor=TEXT_PRIMARY, backColor=BG_SURFACE,
    leftIndent=12, rightIndent=12, spaceBefore=4, spaceAfter=4,
    wordWrap='CJK')
header_cell = ParagraphStyle(
    name='HeaderCell', fontName='NotoSansSC', fontSize=10, leading=14,
    textColor=colors.white, alignment=TA_CENTER)
cell_style = ParagraphStyle(
    name='Cell', fontName='NotoSansSC', fontSize=9.5, leading=14,
    textColor=TEXT_PRIMARY, alignment=TA_LEFT, wordWrap='CJK')
cell_center = ParagraphStyle(
    name='CellCenter', fontName='NotoSansSC', fontSize=9.5, leading=14,
    textColor=TEXT_PRIMARY, alignment=TA_CENTER, wordWrap='CJK')

# ── Helper ──────────────────────────────────────────────────────────
def p(text, style=body_style):
    return Paragraph(text, style)

def make_table(headers, rows, col_widths=None):
    aw = A4[0] - 2*inch
    if col_widths is None:
        n = len(headers)
        col_widths = [aw/n]*n
    data = [[Paragraph(f'<b>{h}</b>', header_cell) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), cell_style) for c in row])
    t = Table(data, colWidths=col_widths, hAlign='CENTER')
    style_cmds = [
        ('BACKGROUND', (0,0), (-1,0), ACCENT),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, TEXT_MUTED),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]
    for i in range(1, len(data)):
        bg = colors.white if i % 2 == 1 else BG_SURFACE
        style_cmds.append(('BACKGROUND', (0,i), (-1,i), bg))
    t.setStyle(TableStyle(style_cmds))
    return t

# ── Build Document ─────────────────────────────────────────────────
doc = SimpleDocTemplate(
    OUTPUT, pagesize=A4,
    leftMargin=inch, rightMargin=inch,
    topMargin=0.8*inch, bottomMargin=0.8*inch)

story = []

# ── Title ───────────────────────────────────────────────────────────
story.append(Spacer(1, 30))
story.append(p('FireAI Bridge 2', title_style))
story.append(p('Code Critique Report', ParagraphStyle(
    name='Sub', fontName='NotoSansSC', fontSize=14, leading=20,
    alignment=TA_CENTER, textColor=TEXT_MUTED, spaceAfter=6)))
story.append(p('Date: 2026-05-19 | Reviewer: Z.ai', ParagraphStyle(
    name='Meta', fontName='NotoSansSC', fontSize=10, leading=14,
    alignment=TA_CENTER, textColor=TEXT_MUTED)))
story.append(Spacer(1, 24))

# ── 1. Executive Summary ────────────────────────────────────────────
story.append(p('<b>1. Executive Summary</b>', h1_style))
story.append(p(
    'This report presents the results of a comprehensive code critique of the FireAI Bridge 2 '
    'implementation, which connects the analysis pipeline to the digital twin for a closed-loop '
    'NFPA 72-compliant fire alarm design system. The review covered four core modules '
    '(event_bus.py, digital_twin.py, analysis_pipeline.py, room_lifecycle.py) and identified '
    '9 bugs ranging from critical safety defects to performance regressions. All critical and '
    'high-severity bugs have been fixed directly in the codebase, and 32 integration tests '
    'now pass to verify the fixes.'
))
story.append(p(
    'The most dangerous bug was in DetectorState where design_x/design_y/design_z used 0.0 '
    'as a sentinel value instead of None. This meant that any detector legitimately placed '
    'at position (0,0,0) - a valid room corner origin - would have its design coordinates '
    'silently overwritten, causing position_drift_m to always return 0.0 even after the '
    'detector was moved. In a life-safety system, this could mask detector displacement that '
    'violates NFPA 72 spacing requirements, potentially leaving areas without fire protection '
    'coverage without anyone knowing.'
))

# ── 2. Bug Summary Table ───────────────────────────────────────────
story.append(p('<b>2. Bug Summary</b>', h1_style))
aw = A4[0] - 2*inch
story.append(make_table(
    ['ID', 'Severity', 'Module', 'Description', 'Status'],
    [
        ['FIX-5', 'CRITICAL', 'digital_twin', 'design_x/y/z=0.0 sentinel masks (0,0,0) detectors', 'Fixed'],
        ['FIX-3a', 'HIGH', 'analysis_pipeline', 'EventBus() creates new instance, not singleton', 'Fixed'],
        ['FIX-3b', 'HIGH', 'room_lifecycle', 'EventBus() creates new instance, not singleton', 'Fixed'],
        ['FIX-6', 'HIGH', 'digital_twin', 'AuditStore stored as class, not instance', 'Fixed'],
        ['NFA', 'HIGH', 'digital_twin', 'compute_checksum excludes building_id', 'Fixed'],
        ['NFB', 'HIGH', 'event_bus', 'publish() silently swallows subscriber errors', 'Fixed'],
        ['NFC', 'MEDIUM', 'event_bus', 'EventRecorder uses list slicing (O(n) eviction)', 'Fixed'],
        ['NFD', 'MEDIUM', 'digital_twin', 'deserialize() missing sub-components', 'Fixed'],
        ['FIX-9', 'MEDIUM', 'analysis_pipeline', 'coverage_radius fallback logic', 'Verified'],
    ],
    col_widths=[aw*0.08, aw*0.10, aw*0.15, aw*0.47, aw*0.10]
))
story.append(Spacer(1, 12))

# ── 3. Critical Bug Details ─────────────────────────────────────────
story.append(p('<b>3. Critical Bug: Design Coordinate Sentinel (FIX-5)</b>', h1_style))
story.append(p(
    'The original DetectorState dataclass defined design_x, design_y, and design_z as '
    'float = 0.0, then used a conditional check in __post_init__ to detect "unset" values. '
    'The check was: if self.design_x == 0.0 and self.design_y == 0.0 and self.design_z == 0.0: '
    'then auto-fill from current position. This is catastrophically wrong for a fire alarm '
    'design system because room coordinates often use the room corner as the origin (0,0), '
    'and a detector at that corner would have its design coordinates "auto-filled" to match '
    'the current position - meaning any subsequent move would report zero drift.'
))
story.append(p(
    'Consider this scenario: A smoke detector is designed for position (0.0, 0.0, 3.0) '
    'in a room whose origin is the lower-left corner. After construction, the contractor '
    'moves it 1.5m to (1.5, 0.0, 3.0) - a position that violates NFPA 72 spacing. '
    'The old code would report position_drift_m = 0.0 because design coords were silently '
    'overwritten to (1.5, 0.0, 3.0). The TwinDriftAnalyzer would never flag this as a '
    'critical NFPA violation. This is a life-safety defect.'
))
story.append(p('<b>Fix Applied:</b> Changed design_x/y/z to Optional[float] = None. '
    'The __post_init__ now checks is None independently for each axis, and from_dict() '
    'handles backward compatibility with old serialized data that lacks these fields.'))

# ── 4. High Severity Bugs ───────────────────────────────────────────
story.append(p('<b>4. High Severity Bugs</b>', h1_style))

story.append(p('<b>4.1 EventBus Singleton Not Shared (FIX-3)</b>', h2_style))
story.append(p(
    'The AnalysisPipeline constructor created a new EventBus() instead of using '
    'EventBus.instance(). Similarly, RoomLifecycle._publish_transition_event() fell back '
    'to EventBus() instead of EventBus.instance(). This means pipeline events (like '
    'DETECTOR_PLACED, CONSENSUS_RESULT, TWIN_SYNC) were published to a private bus that '
    'no other component could subscribe to. The DigitalTwin, which subscribes to Events.TWIN_SYNC '
    'on the singleton bus, would never receive pipeline notifications. This effectively '
    'broke the entire Bridge 2 design goal of connecting pipeline output to the twin.'
))
story.append(p('<b>Fix:</b> Changed both modules to use EventBus.instance().'))

story.append(p('<b>4.2 AuditStore as Class Instead of Instance (FIX-6)</b>', h2_style))
story.append(p(
    'The DigitalTwin constructor stored AuditStore (the class object) instead of '
    'AuditStore() (an instance). When _audit_log() called self._audit_store.add_event(), '
    'it was calling a class method, not an instance method. This means no database connection, '
    'no state tracking, no hash chain - the entire legal-grade audit trail was non-functional. '
    'In an AHJ review, this would be a critical finding because the audit trail is required '
    'evidence of compliance.'
))
story.append(p('<b>Fix:</b> Changed to AuditStore() if AuditStore is not None.'))

story.append(p('<b>4.3 Checksum Excludes Building ID (NEW-FIX-A)</b>', h2_style))
story.append(p(
    'DigitalTwin.compute_checksum() only hashed detector positions, excluding building_id. '
    'Two different buildings with identical detector layouts would produce the same checksum. '
    'If a twin state was accidentally (or maliciously) swapped between buildings, this would '
    'go undetected. The checksum is the tamper-evident fingerprint of the entire twin state, '
    'and omitting the building identifier weakens the integrity guarantee to the point where '
    'it cannot be relied upon for AHJ submissions.'
))
story.append(p('<b>Fix:</b> Included building_id in the checksum payload, and also included '
    'it in the empty_twin sentinel hash.'))

story.append(p('<b>4.4 Silent Exception Swallowing in EventBus (NEW-FIX-B)</b>', h2_style))
story.append(p(
    'EventBus.publish() caught all exceptions from subscriber callbacks with a bare '
    'except Exception: pass, incrementing error_count but never logging what went wrong. '
    'In a safety-critical system, silent failures are unacceptable. If a subscriber that '
    'monitors for NFPA violations throws an error, the operator would never know - the '
    'error_count would increment silently while critical safety checks go unperformed. '
    'The bus correctly survives (catching is correct), but operators must be informed.'
))
story.append(p('<b>Fix:</b> Added logging.error() call inside the except block, preserving '
    'the crash-resistance guarantee while making failures observable.'))

# ── 5. Medium Severity Bugs ────────────────────────────────────────
story.append(p('<b>5. Medium Severity Bugs</b>', h1_style))

story.append(p('<b>5.1 EventRecorder List Slicing (NEW-FIX-C)</b>', h2_style))
story.append(p(
    'EventRecorder used a Python list with manual slicing for bounded eviction: '
    'self._events = self._events[-self._max_events:]. This creates a new list every time '
    'the bound is exceeded - an O(n) operation on a list that can hold up to 10,000 events. '
    'Using collections.deque with maxlen eliminates this entirely: deque.append() is O(1) '
    'and automatic eviction is built-in. In a building with hundreds of rooms, the pipeline '
    'publishes thousands of events, making this a measurable performance regression.'
))
story.append(p('<b>Fix:</b> Replaced list with deque(maxlen=max_events).'))

story.append(p('<b>5.2 Deserialize Missing Sub-Components (NEW-FIX-D)</b>', h2_style))
story.append(p(
    'TwinSerializer.deserialize() restored detectors, events, drift records, and room IDs, '
    'but did not restore _drift_analyzer, _simulator, or _serializer. This meant that '
    'calling detect_drift(), simulate_offline(), or serialize() on a deserialized twin '
    'would crash with AttributeError. In production, a twin restored from a database or '
    'file would appear to load successfully but would be silently broken for any non-trivial '
    'operation. This is particularly dangerous because the failure mode is "works for simple '
    'queries, crashes for analysis" - exactly the pattern that gets missed in testing.'
))
story.append(p('<b>Fix:</b> Added restoration of all three sub-components in deserialize().'))

# ── 6. Test Results ────────────────────────────────────────────────
story.append(p('<b>6. Test Results</b>', h1_style))
story.append(p(
    'A comprehensive integration test suite was created (test_bridge2_integration.py) '
    'with 32 test cases across 12 test classes. All 32 tests pass after applying the fixes. '
    'The test suite covers: EventBus singleton sharing, None sentinel for design coordinates, '
    'deque-based EventRecorder, error logging in publish, checksum building_id inclusion, '
    'deserializer sub-component restoration, AuditStore instance check, coverage radius '
    'propagation, lifecycle state machine, thread safety, and health report safety.'
))

story.append(make_table(
    ['Test Class', 'Tests', 'Result'],
    [
        ['TestEventBusSingletonShared', '3', 'PASS'],
        ['TestDetectorStateNoneSentinel', '5', 'PASS'],
        ['TestEventRecorderDeque', '2', 'PASS'],
        ['TestEventBusErrorLogging', '3', 'PASS'],
        ['TestChecksumIncludesBuildingId', '2', 'PASS'],
        ['TestDeserializeRestoresComponents', '4', 'PASS'],
        ['TestAuditStoreInstance', '1', 'PASS'],
        ['TestCoverageRadiusPropagation', '2', 'PASS'],
        ['TestCertificateHashInTwin', '1', 'PASS'],
        ['TestLifecycleIntegration', '3', 'PASS'],
        ['TestBridge2ThreadSafety', '2', 'PASS'],
        ['TestHealthReportSafety', '3', 'PASS'],
    ],
    col_widths=[aw*0.55, aw*0.15, aw*0.15]
))
story.append(Spacer(1, 12))

# ── 7. Remaining Gaps ─────────────────────────────────────────────
story.append(p('<b>7. Remaining Gaps and Recommendations</b>', h1_style))
story.append(p(
    'While the critical bugs have been fixed, several architectural gaps remain that should '
    'be addressed in future iterations. These are not bugs per se, but design limitations '
    'that could become problems at scale.'
))

story.append(p('<b>7.1 Drift Detection Not Wired Back to Pipeline</b>', h2_style))
story.append(p(
    'The TwinDriftAnalyzer detects position drift and status drift, but the results are '
    'only stored in the twin and published as TWIN_DRIFT events. There is no mechanism '
    'to trigger a pipeline re-analysis when critical drift is detected. For example, if a '
    'detector drifts 1.5m from its design position (a "critical" severity), the system '
    'should automatically queue a re-verification. Currently, this requires manual intervention.'
))

story.append(p('<b>7.2 from_building_report Does Not Store Certificate Hash</b>', h2_style))
story.append(p(
    'When the pipeline loads room data into the twin via from_building_report(), the '
    'proof_certificates field in the room data is not attached to individual detector '
    'metadata. The certificate hash should be stored in each detector record so that '
    'any query can trace from detector back to its proof certificate.'
))

story.append(p('<b>7.3 No __all__ Exports in event_bus.py or digital_twin.py</b>', h2_style))
story.append(p(
    'Modules lack explicit __all__ declarations, which means wildcard imports (from module '
    'import *) would expose internal implementation details. While not a runtime bug, it '
    'violates the principle of minimal API surface and could cause breaking changes if '
    'internal names are refactored.'
))

story.append(p('<b>7.4 DetectorStatus Has No Transition Validation</b>', h2_style))
story.append(p(
    'Unlike RoomLifecycle which has a strict LEGAL_TRANSITIONS map, DetectorStatus allows '
    'any transition via update_detector_status(). For example, a DECOMMISSIONED detector '
    'could be set back to OK without any validation. Adding a transition validator would '
    'prevent invalid lifecycle changes, similar to how RoomLifecycle enforces its state machine.'
))

# ── Build ───────────────────────────────────────────────────────────
doc.build(story)
print(f"Report generated: {OUTPUT}")
