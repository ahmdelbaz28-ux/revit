"""conftest for fireai core tests — pre-import numpy to avoid coverage reload issues."""

import numpy  # noqa: F401 — must be imported before coverage collector
