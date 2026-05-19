"""
dwg_parser.py — FireAI DWG Parser
SAFETY-CRITICAL: Reads DWG via LibreDWG tools.

DEPENDENCY: LibreDWG tools (dxf-out) must be installed.
Installation: sudo apt install libredwg-tools

If not available, converts DWG to DXF using external tools,
then delegates to DXFParser.
"""

import subprocess
import tempfile
import os
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger("fireai.dwg_parser")


# ═══════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════

class DWGConversionError(Exception):
    """Raised when DWG → DXF conversion fails."""
    pass


# ═══════════════════════════════════════════════════════
# DATA CLASS
# ═══════════════════════════════════════════════════════

@dataclass
class DWGParseResult:
    """Result of parsing a DWG file."""
    source_file: str
    success: bool
    room_count: int = 0
    conversion_time_s: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════
# DWG PARSER
# ═══════════════════════════════════════════════════════

class DWGParser:
    """
    Parses DWG files via LibreDWG conversion.
    
    USAGE:
        parser = DWGParser()
        result = parser.parse("building.dwg")
        
        if result.success:
            print(f"Found {result.room_count} rooms")
    """

    DXF_OUT_CMD = "dxf-out"

    def __init__(self):
        """Initialize parser."""
        self._tool_checked = False
        self._tool_available = False

    def _check_tool(self) -> bool:
        """Check if dxf-out is available."""
        if self._tool_checked:
            return self._tool_available
            
        try:
            result = subprocess.run(
                [self.DXF_OUT_CMD, "--version"],
                capture_output=True,
                timeout=5
            )
            self._tool_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._tool_available = False
            
        self._tool_checked = True
        return self._tool_available

    def parse(self, dwg_path: str) -> DWGParseResult:
        """
        Parse DWG file to rooms.
        
        Args:
            dwg_path: Path to .dwg file
            
        Returns:
            DWGParseResult with room count
        """
        import time
        start = time.monotonic()
        
        result = DWGParseResult(source_file=dwg_path, success=False)
        
        # Step 0: Verify file exists
        if not Path(dwg_path).exists():
            result.errors.append(f"File not found: {dwg_path}")
            return result
            
        # Step 1: Check LibreDWG
        if not self._check_tool():
            result.errors.append(
                "LibreDWG not installed. Install with: sudo apt install libredwg-tools"
            )
            return result
            
        # Step 2: Convert DWG → DXF
        try:
            dxf_path = self._convert_to_dxf(dwg_path)
        except DWGConversionError as e:
            result.errors.append(str(e))
            return result
            
        # Step 3: Parse DXF
        try:
            from parsers.dxf_parser import DXFParser
            parser = DXFParser(min_area=2.0)
            dxf_result = parser.parse(dxf_path)
            
            result.room_count = dxf_result.room_count
            result.warnings = dxf_result.warnings
            result.success = dxf_result.room_count > 0
            result.errors = dxf_result.errors
            
        finally:
            # Clean up temp file
            if dxf_path != dwg_path:
                try:
                    os.unlink(dxf_path)
                except:
                    pass
                    
        result.conversion_time_s = round(time.monotonic() - start, 3)
        return result

    def _convert_to_dxf(self, dwg_path: str) -> str:
        """Convert DWG to DXF using dxf-out."""
        # Create temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".dxf", prefix="fireai_dwg_")
        os.close(temp_fd)
        
        cmd = [self.DXF_OUT_CMD, "--file", dwg_path, "--output", temp_path]
        
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if proc.returncode != 0:
                error = proc.stderr.decode() or proc.stdout.decode()
                raise DWGConversionError(f"dxf-out failed: {error}")
                
            if not Path(temp_path).exists() or Path(temp_path).stat().st_size == 0:
                raise DWGConversionError("Empty DXF output")
                
            return temp_path
            
        except subprocess.TimeoutExpired:
            raise DWGConversionError("Conversion timeout")


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════

def parse_dwg(dwg_path: str) -> DWGParseResult:
    """Quick parse DWG file."""
    parser = DWGParser()
    return parser.parse(dwg_path)