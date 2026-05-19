"""Elite Drawing Analyzer — safety-grade drawing intelligence."""
__version__ = "0.2.0"
from .pipeline import analyze_file, teach, Report
from .intelligence.knowledge_base import KnowledgeBase
from .intelligence.classifier import SymbolClassifier
from .intelligence.active_learning import review_pending, submit_feedback, metrics
from .reporting.overlay import render_overlay
from .reporting.html_report import generate_report_html
