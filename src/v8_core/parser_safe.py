"""
v8_core/parser_safe.py
===================
PATCH 6: File Lock + Re-validate Hash Before Parse
Priority: HIGH

This module provides safe parsing with file locking and hash re-validation
to prevent race conditions in concurrent drawing processing.

Integration:
1. gate = SafeParserGate(".parser_cache")
2. result = gate.parse_with_lock("drawing.dwg", my_parser_function)
"""

import os
import json
import fcntl
import hashlib
from pathlib import Path
from typing import Callable, Any, Optional
from datetime import datetime


class SafeParserGate:
    """Parser gate with file locking + hash re-validation."""
    
    def __init__(self, cache_path: str = ".parser_cache"):
        """
        Args:
            cache_path: Directory for cached parse results
        """
        self.cache_path = Path(cache_path)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        
        # Ensure directory is writable
        if not os.access(self.cache_path, os.W_OK):
            raise PermissionError(f"Cache directory not writable: {cache_path}")
    
    def compute_file_hash(self, file_path: str) -> str:
        """
        Compute SHA256 hash of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            64-character hex SHA256 hash
        """
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            # Read in 8KB chunks to handle large files
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def get_cache_file(self, file_path: str, file_hash: str) -> Path:
        """
        Generate cache file path for a drawing.
        
        Args:
            file_path: Path to drawing file
            file_hash: SHA256 hash of drawing
            
        Returns:
            Path to cache JSON file
        """
        stem = Path(file_path).stem
        cache_key = f"{stem}_{file_hash}.json"
        return self.cache_path / cache_key
    
    def parse_with_lock(
        self,
        file_path: str,
        parser_fn: Callable[[str], dict],
        revalidate: bool = True
    ) -> dict:
        """
        Parse with file lock + optional hash re-validation.
        
        Process:
        1. Acquire exclusive lock on file
        2. Compute hash
        3. Check cache
        4. If miss, parse
        5. If revalidate enabled, verify hash before/after cache
        6. Store result
        7. Release lock
        
        Args:
            file_path: Path to drawing file to parse
            parser_fn: Function that parses drawing (should return dict)
            revalidate: Whether to revalidate hash after parsing
            
        Returns:
            Parsed result dict
            
        Raises:
            RuntimeError: If file was modified during parsing
            FileNotFoundError: If drawing file doesn't exist
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Drawing not found: {file_path}")
        
        # Create lock file in cache directory
        lock_file = self.cache_path / f"{file_path.stem}.lock"
        
        with open(lock_file, 'w') as lockf:
            # Acquire exclusive lock (blocks until available)
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            
            try:
                # Compute initial hash BEFORE parsing
                initial_hash = self.compute_file_hash(str(file_path))
                cache_file = self.get_cache_file(str(file_path), initial_hash)
                
                # Check cache
                if cache_file.exists():
                    try:
                        with open(cache_file) as f:
                            cached = json.load(f)
                        
                        # Re-validate: file hash shouldn't have changed
                        if revalidate:
                            current_hash = self.compute_file_hash(str(file_path))
                            if current_hash != initial_hash:
                                print(f"[!] File modified during cache read: {file_path.name}")
                                # Don't use cache, re-parse
                            else:
                                cached['_cached_at'] = datetime.utcnow().isoformat()
                                return cached
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"[!] Cache corrupted ({e}), re-parsing...")
                
                # Cache miss or invalid: parse the file
                print(f"[*] Parsing {file_path.name}...")
                result = parser_fn(str(file_path))
                
                # Add metadata
                result['_parsed_hash'] = initial_hash
                result['_parsed_at'] = datetime.utcnow().isoformat()
                
                # Re-validate AFTER parsing (detect mid-parse modification)
                if revalidate:
                    final_hash = self.compute_file_hash(str(file_path))
                    if final_hash != initial_hash:
                        raise RuntimeError(
                            f"File was modified during parsing: {file_path.name}. "
                            "Aborting cache write to prevent corruption."
                        )
                
                # Write cache
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(result, f, indent=2)
                    print(f"[✓] Cached: {cache_file.name}")
                except IOError as e:
                    print(f"[!] Cache write failed: {e}")
                
                return result
            
            finally:
                # Release lock
                fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
    
    def invalidate_cache(self, file_path: str) -> bool:
        """
        Invalidate cache for a specific file.
        
        Args:
            file_path: Path to drawing file
            
        Returns:
            True if cache was invalidated
        """
        file_path = Path(file_path)
        hash_val = self.compute_file_hash(str(file_path))
        cache_file = self.get_cache_file(str(file_path), hash_val)
        
        if cache_file.exists():
            cache_file.unlink()
            print(f"[✓] Cache invalidated: {cache_file.name}")
            return True
        
        return False
    
    def clear_all_cache(self) -> int:
        """
        Clear all cached parse results.
        
        Returns:
            Number of files deleted
        """
        count = 0
        for cache_file in self.cache_path.glob("*_.json"):
            cache_file.unlink()
            count += 1
        
        print(f"[✓] Cleared {count} cached files")
        return count
    
    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        files = list(self.cache_path.glob("*_.json"))
        total_size = sum(f.stat().st_size for f in files)
        
        return {
            'cache_dir': str(self.cache_path),
            'file_count': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / 1024 / 1024, 2)
        }


def parse_with_gate(
    file_path: str,
    parser_fn: Callable[[str], dict],
    cache_path: str = ".parser_cache"
) -> dict:
    """
    Convenience function for safe parsing.
    
    Args:
        file_path: Path to drawing file
        parser_fn: Parser function
        cache_path: Cache directory
        
    Returns:
        Parsed result
    """
    gate = SafeParserGate(cache_path)
    return gate.parse_with_lock(file_path, parser_fn)


# INTEGRATION GUIDE:
# ================
#
# Step 1: Initialize gate
#   from src.v8_core.parser_safe import SafeParserGate
#   gate = SafeParserGate(".parser_cache")
#
# Step 2: Define parser function
#   def my_parser(dwg_path: str) -> dict:
#       # Your DXF/DWG parsing logic here
#       return {"devices": [...], "loops": [...]}
#
# Step 3: Parse with lock
#   result = gate.parse_with_lock("building.dwg", my_parser)
#
# Step 4: Check results
#   print(f"Found {len(result['devices'])} devices")
#
# Step 5: Invalidate if needed
#   gate.invalidate_cache("building.dwg")
#
# SECURITY NOTES:
# =============
# - fcntl.LOCK_EX prevents concurrent access to same file
# - Hash re-validation catches tampering during parse
# - Cache corruption is handled gracefully (re-parse)