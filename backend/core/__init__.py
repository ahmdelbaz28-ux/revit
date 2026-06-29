"""
Backend core package placeholder.

The top‑level ``core`` package provides the canonical data models and database.
When ``backend`` is added to ``sys.path`` before the project root (as happens
in some test helpers), Python may resolve the import name ``core`` to this
package, which would break imports. To avoid that, this module does **nothing**
apart from a short docstring; the real ``core`` package will be found via the
project‑root entry in ``sys.path`` (which is inserted by tests). Backend‑specific
submodules (e.g. ``backend.core.redis_client``) can still be imported directly.
"""

# No code – the top‑level ``core`` package will be imported from the project root.

