"""
tests/test_digital_twin_path_security.py — P0.2 regression tests
================================================================

Regression coverage for the path-traversal fix in
backend/routers/digital_twin.py::_safe_resolve_upload_path().

The pre-P0.2 implementation used os.path.normpath + str.startswith,
which is bypassable. These tests verify the new implementation uses
the centralised parsers._path_security.validate_input_path() helper
and correctly rejects traversal attempts while accepting legitimate
uploads.

Per agent.md Rule 10 — these tests are NEVER modified; only production
code is modified. A failure here means production code is wrong.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException


# ── Fixture: clean FIREAI_UPLOAD_DIR + allowed-bases env ────────────────────


@pytest.fixture
def isolated_upload_dir(monkeypatch, tmp_path):
    """Point FIREAI_UPLOAD_DIR and FIREAI_ALLOWED_UPLOAD_DIRS at a tmp dir.

    The path-security helper requires the resolved file to live under one
    of FIREAI_ALLOWED_UPLOAD_DIRS. We use the pytest tmp_path (which is a
    subdir of /tmp on Linux) so it is already covered by the helper's
    default allow-list, but we also set FIREAI_UPLOAD_DIR explicitly to
    avoid accidentally reading the operator's working directory.

    IMPORTANT: We deliberately add ONLY tmp_path (the upload dir's parent)
    to FIREAI_ALLOWED_UPLOAD_DIRS — NOT the system temp dir's other
    children, NOT /etc, NOT /home. This means an absolute path or symlink
    pointing OUTSIDE tmp_path will be rejected with UnsafePathError.
    """
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FIREAI_UPLOAD_DIR", str(upload_dir))
    # Allow ONLY the test's own tmp_path — anything outside is a traversal.
    monkeypatch.setenv("FIREAI_ALLOWED_UPLOAD_DIRS", str(tmp_path))
    # Ensure FIREAI_ENV is not "development" so Path.cwd() is not added
    # to the allow-list — we want a tight, predictable allow-list here.
    monkeypatch.delenv("FIREAI_ENV", raising=False)
    return upload_dir


@pytest.fixture
def safe_filename_in_upload_dir(isolated_upload_dir):
    """Create a real file inside the upload dir and return its basename."""
    p = isolated_upload_dir / "legit_file.rvt"
    p.write_bytes(b"fake rvt payload")
    return p.name


# ── Import target (deferred so the fixture can monkeypatch env first) ──────


def _import_target():
    from backend.routers.digital_twin import _safe_resolve_upload_path
    return _safe_resolve_upload_path


# ── Acceptance tests ────────────────────────────────────────────────────────


class TestSafeResolveUploadPathAcceptance:
    """Legitimate files inside the upload dir are accepted."""

    def test_legitimate_file_resolves(self, isolated_upload_dir, safe_filename_in_upload_dir):
        """A real file inside the upload dir resolves to an absolute path."""
        fn = _import_target()
        result = fn(safe_filename_in_upload_dir)
        # Resolved path must end with the requested filename and live
        # inside the upload dir.
        assert result.endswith(safe_filename_in_upload_dir)
        assert str(isolated_upload_dir) in result
        # The file must exist at the resolved path
        assert Path(result).exists()

    def test_extension_allowed_for_any(self, isolated_upload_dir):
        """Unlike revit.py, the digital_twin download endpoint does NOT
        restrict by extension — it serves whatever was uploaded for download.
        Verify a non-RVT file (e.g. .txt) is allowed."""
        p = isolated_upload_dir / "notes.txt"
        p.write_text("hi")
        fn = _import_target()
        result = fn("notes.txt")
        assert result.endswith("notes.txt")


# ── Path-traversal rejection tests ─────────────────────────────────────────


class TestSafeResolveUploadPathTraversalRejection:
    """Path-traversal attempts MUST be rejected.

    Security-correctness rule: the function MUST NEVER return a path
    outside the upload dir. The exact HTTP status (400 vs 404) for
    non-existent traversal attempts is implementation-defined — what
    matters is that NO file outside the upload dir is ever served.

    For traversal attempts that POINT AT AN EXISTING FILE outside the
    upload dir (the actual attack scenario), the function MUST raise
    HTTP 400 (security rejection), NOT 200/return-a-path.
    """

    def test_dotdot_traversal_to_existing_outside_file_rejected(
        self, isolated_upload_dir, tmp_path, monkeypatch
    ):
        """'../../../etc/passwd' must be rejected when /etc/passwd exists.

        This is the real attack scenario: the attacker constructs a path
        that resolves to a real, sensitive file outside the upload dir.
        The function MUST raise HTTP 400 (security rejection).
        """
        # Use /etc/passwd which exists on Linux/macOS. On systems without
        # it, skip rather than weaken the assertion.
        etc_passwd = Path("/etc/passwd")
        if not etc_passwd.exists():
            pytest.skip("/etc/passwd not available on this OS")
        # Compute the relative-traversal path from upload_dir to /etc/passwd.
        # We do NOT add /etc to the allow-list (the fixture only allows tmp_path).
        # The traversal string `../../../etc/passwd` should resolve to /etc/passwd
        # which is outside the allow-list.
        fn = _import_target()
        # Try several traversal depths to ensure at least one escapes
        for depth in range(2, 8):
            traversal = "../" * depth + "etc/passwd"
            with pytest.raises(HTTPException) as exc_info:
                fn(traversal)
            # Must NOT be 200/return — must raise. Accept 400 or 404
            # (404 is acceptable because the unresolved literal path may
            # not exist; what matters is NO outside file is served).
            assert exc_info.value.status_code in (400, 404), (
                f"Traversal '{traversal}' yielded {exc_info.value.status_code}; "
                f"must be 400 (security) or 404 (not-found), NEVER 200."
            )

    def test_dotdot_traversal_to_existing_outside_file_rejects_with_400_when_resolvable(
        self, isolated_upload_dir, tmp_path
    ):
        """When the traversal string resolves to a real existing file
        OUTSIDE the allowed base, the function MUST return HTTP 400.

        We construct this by creating a real file in a directory that is
        NOT in the allow-list. We cannot use /tmp because the path-security
        helper ALWAYS allows /tmp (used for parser intermediate files).
        So we create a file in $HOME instead, which is never auto-allowed.
        """
        home = os.environ.get("HOME") or "/root"
        if not os.path.isdir(home):
            pytest.skip("$HOME not available — cannot construct outside-file test")
        import uuid
        unique = f".fireai_p02_test_{uuid.uuid4().hex[:8]}.txt"
        outside_file = Path(home) / unique
        try:
            outside_file.write_text("this should not be served")
            # Verify it's actually outside tmp_path AND outside /tmp
            try:
                outside_file.resolve().relative_to(tmp_path.resolve())
                pytest.skip("outside_file ended up inside tmp_path — can't test escape")
            except ValueError:
                pass
            # Confirm the file is NOT auto-allowed by _resolve_allowed_bases
            from parsers._path_security import _resolve_allowed_bases
            allowed = _resolve_allowed_bases()
            in_allowed = False
            for b in allowed:
                try:
                    outside_file.resolve().relative_to(b)
                    in_allowed = True
                    break
                except ValueError:
                    continue
            if in_allowed:
                pytest.skip(
                    f"outside_file {outside_file} is in allowed bases {allowed} "
                    f"— cannot test escape in this environment"
                )
            # Build a traversal: from upload_dir (tmp_path/uploads), we need
            # to reach $HOME/unique. Use an absolute path as the "filename"
            # — that's the simplest realistic attack vector.
            fn = _import_target()
            with pytest.raises(HTTPException) as exc_info:
                fn(str(outside_file))
            assert exc_info.value.status_code == 400, (
                f"Traversal to existing outside file must yield 400 (security), "
                f"got {exc_info.value.status_code}. Detail: {exc_info.value.detail}"
            )
        finally:
            try:
                outside_file.unlink()
            except FileNotFoundError:
                pass

    def test_absolute_path_to_existing_outside_file_rejected(
        self, isolated_upload_dir, tmp_path
    ):
        """An absolute path that exists but lives outside the upload dir
        AND outside the always-allowed /tmp dir must be rejected with
        400 (security), NOT served."""
        home = os.environ.get("HOME") or "/root"
        if not os.path.isdir(home):
            pytest.skip("$HOME not available — cannot construct outside-file test")
        import uuid
        unique = f".fireai_p02_abs_{uuid.uuid4().hex[:8]}.txt"
        outside_file = Path(home) / unique
        try:
            outside_file.write_text("this should not be served")
            # Confirm not auto-allowed
            from parsers._path_security import _resolve_allowed_bases
            allowed = _resolve_allowed_bases()
            in_allowed = False
            for b in allowed:
                try:
                    outside_file.resolve().relative_to(b)
                    in_allowed = True
                    break
                except ValueError:
                    continue
            if in_allowed:
                pytest.skip(
                    f"outside_file {outside_file} is in allowed bases {allowed} "
                    f"— cannot test escape in this environment"
                )
            fn = _import_target()
            with pytest.raises(HTTPException) as exc_info:
                # Pass an absolute path as "filename"
                fn(str(outside_file))
            assert exc_info.value.status_code == 400, (
                f"Absolute outside path must yield 400 (security), "
                f"got {exc_info.value.status_code}. Detail: {exc_info.value.detail}"
            )
        finally:
            try:
                outside_file.unlink()
            except FileNotFoundError:
                pass

    def test_null_byte_in_filename_rejected(self, isolated_upload_dir):
        """Null byte truncates C strings — must be rejected before any FS op.

        Null byte check is the FIRST check in validate_input_path (before
        existence), so it MUST raise UnsafePathError → HTTP 400 even
        though no file exists.
        """
        fn = _import_target()
        with pytest.raises(HTTPException) as exc_info:
            fn("safe.txt\x00../../etc/passwd")
        assert exc_info.value.status_code == 400, (
            f"Null byte must yield 400 (security), got {exc_info.value.status_code}"
        )

    def test_leading_dash_rejected(self, isolated_upload_dir):
        """Paths starting with '-' can be interpreted as flags by binaries.

        Leading-dash check is the SECOND check in validate_input_path
        (before existence), so it MUST raise UnsafePathError → HTTP 400
        even though no file named "-some-filename" exists.
        """
        fn = _import_target()
        with pytest.raises(HTTPException) as exc_info:
            fn("-some-filename")
        assert exc_info.value.status_code == 400, (
            f"Leading dash must yield 400 (security), got {exc_info.value.status_code}"
        )

    def test_symlink_escape_rejected(self, isolated_upload_dir):
        """A symlink inside upload_dir pointing OUTSIDE the allowed base
        must be rejected — the resolved target is what matters, not the
        link location."""
        etc_passwd = Path("/etc/passwd")
        if not etc_passwd.exists():
            pytest.skip("/etc/passwd not available on this OS")
        link = isolated_upload_dir / "etc_passwd_link"
        try:
            os.symlink(etc_passwd, link)
        except (OSError, PermissionError):
            pytest.skip("Cannot create symlinks in this environment")
        fn = _import_target()
        with pytest.raises(HTTPException) as exc_info:
            fn("etc_passwd_link")
        assert exc_info.value.status_code == 400, (
            f"Symlink escape must yield 400 (security), "
            f"got {exc_info.value.status_code}. Detail: {exc_info.value.detail}"
        )


# ── Missing-file tests ─────────────────────────────────────────────────────


class TestSafeResolveUploadPathMissingFile:
    """A missing but otherwise-safe filename must return 404, not 500."""

    def test_missing_file_returns_404(self, isolated_upload_dir):
        fn = _import_target()
        with pytest.raises(HTTPException) as exc_info:
            fn("this_file_does_not_exist.rvt")
        assert exc_info.value.status_code == 404, (
            f"Missing file must yield 404, got {exc_info.value.status_code}"
        )

