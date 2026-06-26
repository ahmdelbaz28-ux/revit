"""FireAI Background Worker Package — Celery-based async task execution."""

from backend.worker.celery_app import celery_app, run_analysis_task

__all__ = ["celery_app", "run_analysis_task"]
