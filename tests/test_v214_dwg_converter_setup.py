"""
test_v214_dwg_converter_setup.py — V214 regression tests for DWG converter
infrastructure (requirements-optional.txt + Dockerfile + Windows setup script).

Verifies that:
  1. requirements-optional.txt documents the LibreDWG/ODA binaries
  2. Dockerfile installs libredwg-tools in the runtime stage
  3. The Windows setup script exists and is non-empty
  4. dwg_converter.py still supports the 3 binaries (V213)
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestV214DwgConverterInfrastructure:
    """V214: Verify DWG converter infrastructure is in place."""

    def test_requirements_optional_documents_libredwg(self):
        """requirements-optional.txt must document LibreDWG installation."""
        req_path = REPO_ROOT / "requirements-optional.txt"
        content = req_path.read_text(encoding="utf-8")
        assert "libredwg" in content.lower(), (
            "requirements-optional.txt must mention libredwg for DWG conversion"
        )
        assert "dwg2dxf" in content, (
            "requirements-optional.txt must mention dwg2dxf binary"
        )
        assert "ODAFileConverter" in content, (
            "requirements-optional.txt must mention ODAFileConverter"
        )

    def test_requirements_optional_has_install_instructions(self):
        """requirements-optional.txt must include install instructions for
        at least Linux, macOS, and Windows.
        """
        req_path = REPO_ROOT / "requirements-optional.txt"
        content = req_path.read_text(encoding="utf-8")
        assert "apt-get" in content, "Must include Linux apt-get instructions"
        assert "brew" in content, "Must include macOS brew instructions"
        assert "Windows" in content or "windows" in content.lower(), (
            "Must include Windows instructions"
        )

    def test_dockerfile_installs_libredwg(self):
        """Dockerfile must install libredwg-tools in the runtime stage."""
        dockerfile_path = REPO_ROOT / "Dockerfile"
        content = dockerfile_path.read_text(encoding="utf-8")
        assert "libredwg-tools" in content, (
            "Dockerfile must install libredwg-tools for real DWG→DXF conversion"
        )
        assert "apt-get install" in content
        assert "dwg2dxf --version" in content or "dwg2dxf" in content, (
            "Dockerfile should verify dwg2dxf is available after install"
        )

    def test_dockerfile_cleans_apt_cache(self):
        """Dockerfile must clean apt cache to keep image small."""
        dockerfile_path = REPO_ROOT / "Dockerfile"
        content = dockerfile_path.read_text(encoding="utf-8")
        assert "apt-get clean" in content, "Must clean apt cache"
        assert "/var/lib/apt/lists/*" in content, "Must remove apt lists"

    def test_windows_setup_script_exists(self):
        """The Windows setup script must exist and be non-empty."""
        script_path = REPO_ROOT / "scripts" / "install_dwg_converter_windows.ps1"
        assert script_path.exists(), (
            "Windows setup script must exist at scripts/install_dwg_converter_windows.ps1"
        )
        content = script_path.read_text(encoding="utf-8")
        assert len(content) > 500, (
            f"Windows setup script is too short ({len(content)} chars) — expected full implementation"
        )

    def test_windows_setup_script_downloads_libredwg(self):
        """The Windows setup script must download LibreDWG from gitlab."""
        script_path = REPO_ROOT / "scripts" / "install_dwg_converter_windows.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "gitlab.com/libredwg" in content, (
            "Must download LibreDWG from gitlab.com/libredwg"
        )
        assert "Invoke-WebRequest" in content, "Must use Invoke-WebRequest to download"
        assert "Expand-Archive" in content, "Must extract the zip"
        assert "PATH" in content, "Must add to PATH"

    def test_windows_setup_script_documents_oda(self):
        """The Windows setup script must also document ODA File Converter
        as an alternative.
        """
        script_path = REPO_ROOT / "scripts" / "install_dwg_converter_windows.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "ODAFileConverter" in content, "Must document ODA File Converter"
        assert "opendesign.com" in content, "Must link to ODA download page"

    def test_dwg_converter_supports_3_binaries(self):
        """dwg_converter.py must still support the 3 binaries (V213)."""
        from qomn_fire.parsers.dwg_converter import DwgConverter
        assert "dwg2dxf" in DwgConverter._CONVERTER_BINARIES
        assert "ODAFileConverter" in DwgConverter._CONVERTER_BINARIES
        assert "oda_file_converter" in DwgConverter._CONVERTER_BINARIES
