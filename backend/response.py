"""
backend/response.py — Unified API response helpers.

All API endpoints MUST use these helpers to return consistent response format.
The frontend expects: {success, data?, error?, message?, timestamp}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def success(data: Any = None, message: str = "") -> Dict[str, Any]:
    """Return a successful API response."""
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def error(message: str, data: Any = None) -> Dict[str, Any]:
    """Return an error API response."""
    return {
        "success": False,
        "data": data,
        "error": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def paginated(data: list, total: int, page: int, page_size: int, total_pages: int) -> Dict[str, Any]:
    """Return a paginated response."""
    return success({
        "items": data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    })
