#!/usr/bin/env python3
"""
remove_file_level_nosonar.py — Safely remove file-level '# NOSONAR' from Python files.

This script replaces the file-level '# NOSONAR' suppression (which silences
ALL SonarQube rules for the entire file) with a documentation comment that
points to NOSONAR_AUDIT.md. Per-line justified suppressions are PRESERVED.

Usage:
    python scripts/remove_file_level_nosonar.py <file1> [file2] [file3] ...

Safety:
    - Only modifies files where line 1 is EXACTLY '# NOSONAR'
    - Preserves all other content (including per-line NOSONAR suppressions)
    - Reports what was changed for audit trail
    - Does NOT modify files that don't match the pattern
    - V143 SECURITY FIX: Validates paths to prevent path traversal (S2083)
      — only files within the current working directory are modified.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPLACEMENT_COMMENT = (
    "# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).\n"
    "# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.\n"
)


def _validate_path_safely(filepath: Path) -> Path | None:
    """
    V143 SECURITY FIX (S2083): Validate that the file path is safe.

    Resolves the path and checks that it is within the current working
    directory (or the repo root). This prevents path traversal attacks
    where a malicious CLI argument could escape the intended directory.

    Returns the resolved absolute Path if safe, or None if the path
    is rejected.
    """
    try:
        # Resolve to absolute path, following symlinks
        resolved = filepath.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        print(f"  REJECT {filepath}: cannot resolve ({e})")
        return None

    # Determine the safe root: current working directory
    # (the script is expected to be run from the repo root)
    try:
        safe_root = Path.cwd().resolve(strict=False)
    except (OSError, RuntimeError):
        safe_root = Path(__file__).parent.parent.resolve(strict=False)

    # Check that the resolved path is within the safe root
    try:
        resolved.relative_to(safe_root)
    except ValueError:
        print(f"  REJECT {filepath}: path escapes safe root ({safe_root})")
        return None

    # Reject if the path contains suspicious patterns
    path_str = str(filepath)
    if ".." in path_str.split(os.sep):
        print(f"  REJECT {filepath}: path contains '..' component")
        return None

    return resolved


def remove_file_level_nosonar(filepath: Path) -> bool:
    """
    Remove file-level '# NOSONAR' from the first line of a Python file.

    Returns True if the file was modified, False if it was already clean
    or didn't match the pattern.
    """
    safe_path = _validate_path_safely(filepath)
    if safe_path is None:
        return False

    try:
        content = safe_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"  SKIP {safe_path}: cannot read ({e})")
        return False

    lines = content.split("\n")

    # Check if line 0 (first line) is exactly '# NOSONAR'
    if not lines or lines[0].strip() != "# NOSONAR":
        first = lines[0][:50] if lines else "empty"
        print(f"  SKIP {safe_path}: line 1 is not '# NOSONAR' (got: {first!r})")
        return False

    # Replace line 0 with the documentation comment
    # Keep the rest of the file unchanged
    new_lines = [REPLACEMENT_COMMENT.rstrip("\n")] + lines[1:]
    new_content = "\n".join(new_lines)

    # Ensure file ends with newline
    if not new_content.endswith("\n"):
        new_content += "\n"

    safe_path.write_text(new_content, encoding="utf-8")
    print(f"  DONE {safe_path}")
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: remove_file_level_nosonar.py <file1> [file2] ...", file=sys.stderr)
        return 1

    files = [Path(f) for f in sys.argv[1:]]
    modified = 0
    skipped = 0

    print(f"Processing {len(files)} file(s)...")
    print(f"Safe root: {Path.cwd().resolve()}")
    for f in files:
        if not f.exists():
            print(f"  SKIP {f}: does not exist")
            skipped += 1
            continue
        if remove_file_level_nosonar(f):
            modified += 1
        else:
            skipped += 1

    print(f"\nSummary: {modified} modified, {skipped} skipped")
    return 0 if modified > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
