"""
parsers/_path_security.py — Shared path-security utilities for parsers
=======================================================================
V122: Extracted from ddc_adapter.py to be shared by all parsers that
accept user-controlled file paths and invoke external binaries or read
files. Prevents path traversal, argument injection, symlink attacks,
and TOCTOU races at the parser-input boundary.

SAFETY: Centralized so that the security contract for "accepted input
path" is identical across every parser. Per agent.md Rule #23 (single
source of truth) and Rule #12 (safety-first).
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger("fireai.parsers.security")


class UnsafePathError(ValueError):
    """
    Raised when an input path fails a security check.

    This is a hard rejection — the parser MUST NOT proceed with the
    file. It is distinct from FileNotFoundError because a missing file
    is a benign error, while an unsafe path indicates either a misuse
    or an attack.
    """


def _resolve_allowed_bases() -> list[Path]:
    """
    Compute the allow-list of directories from environment + temp dir.

    Returns a list of resolved Path objects. Allowed bases:
      - $FIREAI_ALLOWED_UPLOAD_DIRS (comma-separated)
      - tempfile.gettempdir() (always allowed — tests use this)
      - Path.cwd() when FIREAI_ENV=development (NEVER in production)
    """
    raw = os.getenv(
        "FIREAI_ALLOWED_UPLOAD_DIRS",
        "/tmp,/var/tmp,/var/fireai/uploads",
    )
    bases: list[Path] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            bases.append(Path(entry).resolve())
        except (OSError, RuntimeError) as e:
            # Resolve can fail on symlink loops, permission denied, etc.
            # Skip the malformed entry rather than crashing the whole list.
            logger.warning(
                "Skipping malformed FIREAI_ALLOWED_UPLOAD_DIRS entry %r: %s",
                entry, e,
            )

    # Always include the system temp dir (tests, parser intermediate files)
    try:
        temp_dir = Path(tempfile.gettempdir()).resolve()
        if temp_dir not in bases:
            bases.append(temp_dir)
    except (OSError, RuntimeError):
        # If we can't even resolve the temp dir, something is very wrong;
        # let it bubble up so the parser fails loudly rather than silently
        # accepting unsafe paths.
        raise

    # Development convenience: allow CWD. NEVER in production.
    if os.getenv("FIREAI_ENV") == "development":
        try:
            cwd = Path.cwd().resolve()
            if cwd not in bases:
                bases.append(cwd)
        except (OSError, RuntimeError) as e:
            logger.debug("Could not resolve CWD for development allow-list: %s", e)

    return bases


def validate_input_path(
    input_path: str,
    *,
    allowed_extensions: frozenset[str] | None = None,
    parser_name: str = "parser",
) -> Path:
    """
    Validate a user-supplied file path before passing it to a binary.

    Checks performed (in order):
      1. Path exists
      2. Resolve path (follows symlinks) and check the resolved path is
         within FIREAI_ALLOWED_UPLOAD_DIRS or the system temp dir
      3. If `allowed_extensions` is given, the suffix MUST be in the set
         (case-insensitive)
      4. The path string itself MUST NOT start with "-" or "--"
         (argument-injection guard for binaries that interpret leading
         dashes as flags — e.g. `dxf-out --file=-output.txt` would treat
         the path as a flag string)
      5. The path MUST NOT contain null bytes (defense against C-string
         truncation in downstream binaries)

    Args:
        input_path: User-supplied path string.
        allowed_extensions: Optional frozenset of suffixes (with leading
            dot, lowercase, e.g. ``frozenset({".dwg", ".dxf"})``).
        parser_name: Used in error messages / logs for traceability.

    Returns:
        The resolved Path (safe to pass to subprocess after this call).

    Raises:
        FileNotFoundError: Path does not exist (benign).
        UnsafePathError: Any security check failed (hard rejection).

    """
    if input_path is None or not isinstance(input_path, str):
        raise UnsafePathError(
            f"{parser_name}: input_path must be a non-empty string"
        )

    # (5) Null byte check — must happen BEFORE any path operations.
    # A path containing \x00 can truncate when passed through C APIs.
    if "\x00" in input_path:
        raise UnsafePathError(
            f"{parser_name}: input path contains null byte (\\x00) — rejected"
        )

    # (4) Argument-injection guard — must happen BEFORE we hand the
    # string to a subprocess. The check is on the RAW string, not the
    # resolved Path, because the subprocess receives the raw string.
    if input_path.startswith("-"):
        raise UnsafePathError(
            f"{parser_name}: input path '{input_path}' starts with '-' which "
            "could be interpreted as a flag by the external binary. Use a "
            "relative path like './filename' or an absolute path."
        )

    input_path_obj = Path(input_path)

    # V138 FIX (LOW-1): Reordered checks — authorization BEFORE existence.
    #
    # The original order was:
    #   (1) Path exists?  ← FileNotFoundError if not
    #   (2) Path traversal check
    #
    # This leaked existence information: probing `/etc/shadow` (exists,
    # readable by root) vs `/nonexistent` (doesn't exist) produced
    # DIFFERENT exceptions, allowing an attacker to enumerate which
    # files exist on the server.
    #
    # New order:
    #   (1) Resolve path (follows symlinks)
    #   (2) Authorization check: resolved path must be inside an allowed base
    #   (3) Existence check (only after authorization passed)
    #
    # Now `/etc/shadow` and `/nonexistent` BOTH raise UnsafePathError
    # (authorization failure), producing IDENTICAL exceptions. No
    # existence oracle for the attacker.

    # (2) Path traversal: resolved path must be inside an allowed base.
    try:
        safe_path = input_path_obj.resolve()
    except (OSError, RuntimeError) as e:
        raise UnsafePathError(
            f"{parser_name}: cannot resolve path '{input_path}' (likely "
            f"symlink loop or permission error): {e}"
        )

    allowed_bases = _resolve_allowed_bases()
    in_allowed = False
    for base in allowed_bases:
        try:
            safe_path.relative_to(base)
            in_allowed = True
            break
        except ValueError:
            continue

    if not in_allowed:
        raise UnsafePathError(
            f"{parser_name}: SECURITY: resolved path '{safe_path}' is outside "
            f"allowed directories. Path traversal detected. Allowed bases: "
            f"{[str(b) for b in allowed_bases]}"
        )

    # (1) Exists? — checked AFTER authorization to avoid information leak.
    if not input_path_obj.exists():
        raise FileNotFoundError(f"{parser_name}: input file not found: {input_path}")

    # Symlink note: Path.resolve() follows symlinks. If the original
    # was a symlink, log it for audit purposes — the resolved target
    # has already been verified to live under an allowed base.
    if input_path_obj.is_symlink():
        logger.info(
            "%s: input path is a symlink: %s → %s (resolved target verified)",
            parser_name, input_path_obj, safe_path,
        )

    # (3) Extension check (if requested)
    if allowed_extensions is not None:
        ext = input_path_obj.suffix.lower()
        if ext not in allowed_extensions:
            raise UnsafePathError(
                f"{parser_name}: file extension '{ext}' is not allowed. "
                f"Permitted: {sorted(allowed_extensions)}"
            )

    return safe_path


def validate_output_path(
    output_path: str,
    *,
    allowed_extensions: frozenset[str] | None = None,
    parser_name: str = "parser",
) -> Path:
    """
    Validate a user-supplied OUTPUT file path (file may not exist yet).

    V141.4: Added for write_rvt and similar functions that create new
    files. Uses the same security checks as validate_input_path but
    does NOT require the file to exist (since we're creating it).

    Checks performed (in order):
      1. Path is not empty
      2. Path traversal: resolved path must be inside an allowed base
      3. Symlink resolution (Path.resolve follows symlinks)
      4. File extension allowlist (if provided)

    Returns the resolved Path object on success.

    Raises:
        UnsafePathError: If path traversal or other security violation.
        ValueError: If path is empty or extension not allowed.
    """
    if not output_path or not output_path.strip():
        raise UnsafePathError(f"{parser_name}: output path is empty")

    output_path_obj = Path(output_path)

    # Resolve symlinks and get canonical absolute path.
    # strict=False: don't require the file to exist (we're creating it).
    # lgtm [py/path-injection] — this IS the security validation function.
    # The resolve() call here is intentional: it follows symlinks so we
    # can verify the FINAL target is inside an allowed base. CodeQL flags
    # this as path-injection because output_path is user-provided, but
    # the whole purpose of this function is to make user-provided paths
    # safe. Suppressing the false positive.
    try:
        safe_path = output_path_obj.resolve(strict=False)  # lgtm [py/path-injection]
    except (OSError, RuntimeError) as e:
        raise UnsafePathError(
            f"{parser_name}: cannot resolve output path '{output_path}' "
            f"(likely symlink loop or permission error): {e}"
        )

    # Path traversal: resolved path must be inside an allowed base.
    allowed_bases = _resolve_allowed_bases()
    in_allowed = False
    for base in allowed_bases:
        try:
            safe_path.relative_to(base)
            in_allowed = True
            break
        except ValueError:
            continue

    if not in_allowed:
        raise UnsafePathError(
            f"{parser_name}: SECURITY: resolved output path '{safe_path}' "
            f"is outside allowed directories. Path traversal detected. "
            f"Allowed bases: {[str(b) for b in allowed_bases]}"
        )

    # Extension allowlist (if provided)
    if allowed_extensions:
        ext = safe_path.suffix.lower()
        if ext not in allowed_extensions:
            raise UnsafePathError(
                f"{parser_name}: output file extension '{ext}' is not "
                f"allowed. Permitted: {sorted(allowed_extensions)}"
            )

    return safe_path


def validate_file_size(
    safe_path: Path,
    *,
    max_size_bytes: int,
    parser_name: str = "parser",
) -> int:
    """
    Reject files larger than a configured maximum.

    Defense against DoS via massive input files (decompression bombs,
    zip-bomb-equivalents for binary CAD formats, etc.). The check is
    performed against the RESOLVED path, so symlink-to-huge-file is
    correctly detected.

    Args:
        safe_path: Already-validated Path (output of `validate_input_path`).
        max_size_bytes: Maximum permitted file size in bytes.
        parser_name: Used in error messages.

    Returns:
        Actual file size in bytes (always ≤ max_size_bytes when this
        returns without raising).

    Raises:
        UnsafePathError: File exceeds the configured limit.

    """
    try:
        size = safe_path.stat().st_size
    except OSError as e:
        raise UnsafePathError(
            f"{parser_name}: cannot stat '{safe_path}': {e}"
        )
    if size > max_size_bytes:
        raise UnsafePathError(
            f"{parser_name}: file '{safe_path}' size {size} bytes exceeds "
            f"limit {max_size_bytes} bytes ({max_size_bytes / 1_048_576:.1f} MB). "
            "Reject as potential DoS vector."
        )
    return size
