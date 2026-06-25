"""
code_indexer.py — Code Indexing for Code Understanding
=====================================================

Indexes Python files for semantic search and code understanding.
Uses AST-based chunking and vector embeddings.

Features:
- Recursive directory scanning
- AST-based code chunking (functions, classes, imports)
- File type filtering
- Automatic indexing with progress reporting
- Integration with LocalVectorStore

Usage:
    from fireai.infrastructure.code_indexer import CodeIndexer
    
    indexer = CodeIndexer(root_dir=".")
    indexer.index_all()
    
    results = indexer.search("fire alarm placement")
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fireai.infrastructure.context_window_manager import ContextWindowManager
from fireai.infrastructure.local_vector_store import LocalVectorStore

logger = logging.getLogger(__name__)


class CodeIndexer:
    """
    Indexes Python files for semantic code search.
    
    Workflow:
    1. Scan directory for Python files
    2. Parse each file with AST
    3. Chunk by function/class/import boundaries
    4. Store in vector store with metadata
    5. Enable semantic search
    
    Args:
        root_dir: Root directory to index
        exclude_dirs: Directories to exclude (e.g., __pycache__, .git)
        file_extensions: File extensions to index
        max_file_size_kb: Skip files larger than this
    """
    
    def __init__(
        self,
        root_dir: str = ".",
        exclude_dirs: Optional[list[str]] = None,
        file_extensions: Optional[list[str]] = None,
        max_file_size_kb: int = 500,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.exclude_dirs = exclude_dirs or [
            "__pycache__",
            ".git",
            ".pytest_cache",
            "node_modules",
            "venv",
            ".venv",
            "env",
            ".env",
            "dist",
            "build",
            ".tox",
            ".eggs",
            "*.egg-info",
        ]
        self.file_extensions = file_extensions or [".py"]
        self.max_file_size_kb = max_file_size_kb
        
        # Components
        self.context_manager = ContextWindowManager(max_tokens=100000)
        self.vector_store = LocalVectorStore(embedding_mode="tfidf")
        
        # Stats
        self._files_indexed = 0
        self._chunks_indexed = 0
        self._errors = []
    
    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for excl in self.exclude_dirs:
            if excl.startswith("*"):
                # Wildcard pattern
                if path_str.endswith(excl[1:]):
                    return True
            elif excl in path_str:
                return True
        return False
    
    def _should_index(self, path: Path) -> bool:
        """Check if file should be indexed."""
        if not path.is_file():
            return False
        
        if path.suffix not in self.file_extensions:
            return False
        
        if self._should_exclude(path):
            return False
        
        # Check file size
        size_kb = path.stat().st_size / 1024
        if size_kb > self.max_file_size_kb:
            logger.warning(f"Skipping large file: {path} ({size_kb:.1f} KB)")
            return False
        
        return True
    
    def _chunk_file(self, file_path: Path) -> list[dict[str, Any]]:
        """Chunk a Python file by AST structure."""
        chunks = []
        
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            try:
                rel_path = str(file_path.relative_to(self.root_dir))
            except ValueError:
                # Fallback if file is outside root_dir
                rel_path = str(file_path)
            
            # Module docstring
            docstring = ast.get_docstring(tree)
            if docstring:
                chunks.append({
                    "content": docstring,
                    "metadata": {
                        "type": "docstring",
                        "name": "module",
                        "file_path": rel_path,
                    }
                })
            
            # Top-level definitions
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    chunks.extend(self._chunk_class(node, rel_path))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chunks.extend(self._chunk_function(node, rel_path))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    chunks.append({
                        "content": ast.unparse(node),
                        "metadata": {
                            "type": "import",
                            "name": self._get_import_name(node),
                            "file_path": rel_path,
                            "line_start": node.lineno or 0,
                            "line_end": node.end_lineno or 0,
                        }
                    })
                        
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            self._errors.append({"file": str(file_path), "error": str(e)})
        except Exception as e:
            logger.error(f"Error chunking {file_path}: {e}")
            self._errors.append({"file": str(file_path), "error": str(e)})
        
        return chunks
    
    def _chunk_class(self, node: ast.ClassDef, rel_path: str) -> list[dict[str, Any]]:
        """Chunk a class definition."""
        chunks = []
        
        # Class docstring
        docstring = ast.get_docstring(node)
        if docstring:
            chunks.append({
                "content": docstring,
                "metadata": {
                    "type": "docstring",
                    "name": f"{node.name} (class)",
                    "file_path": rel_path,
                    "line_start": node.lineno or 0,
                }
            })
        
        # Class body (truncated if large)
        try:
            class_source = ast.unparse(node)
            if len(class_source) > 5000:
                class_source = class_source[:5000] + "\n# ... (truncated)"
            
            chunks.append({
                "content": class_source,
                "metadata": {
                    "type": "class",
                    "name": node.name,
                    "file_path": rel_path,
                    "line_start": node.lineno or 0,
                    "line_end": node.end_lineno or 0,
                }
            })
        except Exception as e:
            logger.warning(f"Could not unparse class {node.name}: {e}")
        
        return chunks
    
    def _chunk_function(self, node: ast.FunctionDef, rel_path: str) -> list[dict[str, Any]]:
        """Chunk a function definition."""
        chunks = []
        
        # Function docstring
        docstring = ast.get_docstring(node)
        if docstring:
            chunks.append({
                "content": docstring,
                "metadata": {
                    "type": "docstring",
                    "name": f"{node.name} (function)",
                    "file_path": rel_path,
                    "line_start": node.lineno or 0,
                }
            })
        
        # Function signature + body
        try:
            func_source = ast.unparse(node)
            if len(func_source) > 3000:
                func_source = func_source[:3000] + "\n# ... (truncated)"
            
            chunks.append({
                "content": func_source,
                "metadata": {
                    "type": "function",
                    "name": node.name,
                    "file_path": rel_path,
                    "line_start": node.lineno or 0,
                    "line_end": node.end_lineno or 0,
                }
            })
        except Exception as e:
            logger.warning(f"Could not unparse function {node.name}: {e}")
        
        return chunks
    
    def _get_import_name(self, node) -> str:
        """Get import name for display."""
        if isinstance(node, ast.Import):
            return ", ".join(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            return node.module or ".".join(a.name for a in node.names)
        return "unknown"
    
    def index_file(self, file_path: Path) -> int:
        """
        Index a single file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Number of chunks indexed
        """
        if not self._should_index(file_path):
            return 0
        
        chunks = self._chunk_file(file_path)
        
        for chunk in chunks:
            # Add to context manager
            self.context_manager.add(
                content=chunk["content"],
                priority=2 if chunk["metadata"]["type"] in ("class", "function") else 1,
                chunk_type=chunk["metadata"]["type"],
                name=chunk["metadata"].get("name", ""),
                file_path=chunk["metadata"]["file_path"],
                line_start=chunk["metadata"].get("line_start", 0),
                line_end=chunk["metadata"].get("line_end", 0),
            )
            
            # Add to vector store
            self.vector_store.add(
                content=chunk["content"],
                metadata=chunk["metadata"],
            )
        
        self._files_indexed += 1
        self._chunks_indexed += len(chunks)
        
        return len(chunks)
    
    def index_all(self, pattern: str = "**/*.py") -> dict[str, Any]:
        """
        Index all matching files in the root directory.
        
        Args:
            pattern: Glob pattern for files to index
            
        Returns:
            Index statistics
        """
        files = list(self.root_dir.glob(pattern))
        files = [f for f in files if self._should_index(f)]
        
        logger.info(f"Found {len(files)} files to index")
        
        for i, file_path in enumerate(files):
            if i % 50 == 0:
                logger.info(f"Indexing {i}/{len(files)}: {file_path.name}")
            self.index_file(file_path)
        
        return self.get_stats()
    
    def index_directory(self, directory: Path) -> dict[str, Any]:
        """
        Index all Python files in a directory recursively.
        
        Args:
            directory: Directory to index
            
        Returns:
            Index statistics
        """
        files = []
        for root, dirs, filenames in os.walk(directory):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for filename in filenames:
                if any(filename.endswith(ext) for ext in self.file_extensions):
                    files.append(Path(root) / filename)
        
        logger.info(f"Found {len(files)} files to index in {directory}")
        
        for i, file_path in enumerate(files):
            if i % 50 == 0:
                logger.info(f"Indexing {i}/{len(files)}: {file_path.name}")
            self.index_file(file_path)
        
        return self.get_stats()
    
    def search(
        self,
        query: str,
        k: int = 10,
        file_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Search indexed code.
        
        Args:
            query: Search query
            k: Number of results
            file_filter: Optional file path filter
            
        Returns:
            List of search results with chunks
        """
        # Search vector store
        results = self.vector_store.search(query, k=k * 2)
        
        # Filter by file if specified
        if file_filter:
            results = [
                r for r in results
                if file_filter in r["metadata"].get("file_path", "")
            ]
        
        # Limit to k results
        return results[:k]
    
    def search_by_file(self, file_path: str, query: str = "") -> list[dict[str, Any]]:
        """
        Get all chunks from a specific file.
        
        Args:
            file_path: Path to the file
            query: Optional query to rank results
            
        Returns:
            List of chunks from the file
        """
        return self.vector_store.search_by_file(file_path, k=50)
    
    def get_stats(self) -> dict[str, Any]:
        """Get indexer statistics."""
        return {
            "files_indexed": self._files_indexed,
            "chunks_indexed": self._chunks_indexed,
            "context_tokens": self.context_manager.total_tokens,
            "vector_store": self.vector_store.get_stats(),
            "errors": self._errors[:10],  # First 10 errors
        }
    
    def clear(self):
        """Clear all indexed data."""
        self.context_manager.clear()
        self.vector_store.clear()
        self._files_indexed = 0
        self._chunks_indexed = 0
        self._errors.clear()


# Singleton
_indexer: Optional[CodeIndexer] = None


def get_code_indexer(root_dir: str = ".") -> CodeIndexer:
    """Get singleton code indexer."""
    global _indexer
    if _indexer is None:
        _indexer = CodeIndexer(root_dir=root_dir)
    return _indexer


__all__ = [
    "CodeIndexer",
    "get_code_indexer",
]
