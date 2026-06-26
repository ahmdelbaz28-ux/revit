"""
context_window_manager.py — Context Window Management for Code Understanding
=====================================================================

Provides efficient context window management for large codebases:
1. Token counting (tiktoken-based, OpenAI-compatible)
2. Sliding window with priority-based eviction
3. Code-aware chunking (by function/class/file boundaries)
4. Context summarization for overflow

Usage:
    from fireai.infrastructure.context_window_manager import ContextWindowManager

    cwm = ContextWindowManager(max_tokens=128000)
    cwm.add("function foo(): ...", priority=1, metadata={"type": "function"})
    context = cwm.get_context()  # Returns string within token limit
"""

from __future__ import annotations

import ast
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, cast

logger = logging.getLogger(__name__)

# Try to import tiktoken, fall back to simple counter if unavailable
try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    _HAS_TIKTOKEN = False
    logger.warning("tiktoken not installed. Using approximate token counting.")


# Default model for tokenization (cl100k_base = GPT-4/GPT-3.5 turbo)
_DEFAULT_ENCODING = "cl100k_base"


@dataclass
class Chunk:
    """A chunk of text with metadata."""
    content: str
    tokens: int
    priority: int = 1
    chunk_type: str = "text"  # "function", "class", "import", "comment", "docstring"
    name: str = ""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    chunk_id: str = ""

    def __post_init__(self) -> None:
        if not self.chunk_id:
            self.chunk_id = hashlib.md5(
                f"{self.file_path}:{self.line_start}:{self.name}".encode(),
                usedforsecurity=False
            ).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tokens": self.tokens,
            "priority": self.priority,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "chunk_id": self.chunk_id,
        }


class EncodingType(Enum):
    """Supported encoding types for tokenization."""
    CL100K_BASE = "cl100k_base"  # GPT-4, GPT-3.5 turbo
    P50K_BASE = "p50k_base"  # Codex, GPT-3
    P50K_EDIT = "p50k_edit"  # Code editing
    R50K_BASE = "r50k_base"  # GPT-3


class ContextWindowManager:
    """
    Manages context window for large codebases.

    Features:
    - Token counting with tiktoken (OpenAI-compatible)
    - Priority-based chunk management
    - Sliding window with LRU eviction
    - Code-aware chunking (functions, classes, imports)
    - Context summarization for overflow

    Args:
        max_tokens: Maximum tokens in context (default 128000 for GPT-4)
        encoding_name: tiktoken encoding to use
        overlap_tokens: Tokens to overlap between chunks (for context continuity)
    """

    def __init__(
        self,
        max_tokens: int = 128000,
        encoding_name: str = _DEFAULT_ENCODING,
        overlap_tokens: int = 100,
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

        # Initialize encoder
        if _HAS_TIKTOKEN:
            try:
                self.encoder = tiktoken.get_encoding(encoding_name)
                logger.info(f"ContextWindowManager: Using tiktoken encoding '{encoding_name}'")
            except Exception as e:
                logger.warning(f"Failed to load encoding '{encoding_name}': {e}. Using simple counter.")
                self.encoder = None
        else:
            self.encoder = None

        # Chunk storage
        self._chunks: list[Chunk] = []
        self._chunk_map: dict[str, Chunk] = {}  # chunk_id -> Chunk

        # Statistics
        self._total_tokens_added = 0
        self._total_chunks_added = 0

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken or approximate.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if self.encoder:
            return len(self.encoder.encode(text))

        # Fallback: ~4 chars per token (rough approximation)
        return len(text) // 4

    def add(
        self,
        content: str,
        priority: int = 1,
        chunk_type: str = "text",
        name: str = "",
        file_path: str = "",
        line_start: int = 0,
        line_end: int = 0,
    ) -> str:
        """
        Add a chunk to the context.

        Args:
            content: Text content of the chunk
            priority: Priority (higher = more likely to stay when evicting)
            chunk_type: Type of chunk ("function", "class", "import", etc.)
            name: Name of the chunk (function name, class name, etc.)
            file_path: Path to the file this chunk came from
            line_start: Starting line number
            line_end: Ending line number

        Returns:
            chunk_id of the added chunk
        """
        tokens = self.count_tokens(content)

        chunk = Chunk(
            content=content,
            tokens=tokens,
            priority=priority,
            chunk_type=chunk_type,
            name=name,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
        )

        self._chunks.append(chunk)
        self._chunk_map[chunk.chunk_id] = chunk
        self._total_tokens_added += tokens
        self._total_chunks_added += 1

        logger.debug(
            f"Added chunk: {chunk.chunk_id} ({chunk_type}:{name}, "
            f"{tokens} tokens, priority={priority})"
        )

        return chunk.chunk_id

    def add_file(self, file_path: str, content: str) -> list[str]:
        """
        Add a file with automatic chunking by structure.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of chunk_ids
        """
        chunk_ids = []

        try:
            tree = ast.parse(content)

            # Add module-level docstring first (high priority)
            docstring = ast.get_docstring(tree)
            if docstring:
                chunk_ids.append(self.add(
                    content=docstring,
                    priority=2,
                    chunk_type="docstring",
                    name="module",
                    file_path=file_path,
                ))

            # Process top-level definitions
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    chunk_ids.extend(self._chunk_class(node, file_path))
                elif isinstance(node, ast.FunctionDef):
                    chunk_ids.extend(self._chunk_function(node, file_path))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        chunk_ids.append(self.add(
                            content=ast.unparse(node),
                            priority=0,
                            chunk_type="import",
                            name=alias.name,
                            file_path=file_path,
                            line_start=node.lineno or 0,
                            line_end=node.end_lineno or 0,
                        ))
                elif isinstance(node, ast.ImportFrom):
                    chunk_ids.append(self.add(
                        content=ast.unparse(node),
                        priority=0,
                        chunk_type="import",
                        name=node.module or "",
                        file_path=file_path,
                        line_start=node.lineno or 0,
                        line_end=node.end_lineno or 0,
                    ))

        except SyntaxError as e:
            # If AST parsing fails, add entire file as one chunk
            logger.warning(f"AST parsing failed for {file_path}: {e}. Adding as single chunk.")
            chunk_ids.append(self.add(
                content=content,
                priority=1,
                chunk_type="file",
                name=os.path.basename(file_path),
                file_path=file_path,
            ))

        return chunk_ids

    def _chunk_function(self, node: ast.FunctionDef, file_path: str) -> list[str]:
        """Chunk a function definition."""
        chunk_ids = []

        # Function docstring (if any)
        docstring = ast.get_docstring(node)
        if docstring:
            chunk_ids.append(self.add(
                content=docstring,
                priority=3,  # Docstrings are high priority
                chunk_type="docstring",
                name=f"{node.name} (docstring)",
                file_path=file_path,
                line_start=node.lineno or 0,
            ))

        # Function signature + body (truncated if too large)
        func_source = ast.unparse(node)
        tokens = self.count_tokens(func_source)

        if tokens > 2000:
            # Truncate large functions
            func_source = func_source[:8000] + "\n# ... (truncated)"

        chunk_ids.append(self.add(
            content=func_source,
            priority=2,
            chunk_type="function",
            name=node.name,
            file_path=file_path,
            line_start=node.lineno or 0,
            line_end=node.end_lineno or 0,
        ))

        return chunk_ids

    def _chunk_class(self, node: ast.ClassDef, file_path: str) -> list[str]:
        """Chunk a class definition."""
        chunk_ids = []

        # Class docstring
        docstring = ast.get_docstring(node)
        if docstring:
            chunk_ids.append(self.add(
                content=docstring,
                priority=3,
                chunk_type="docstring",
                name=f"{node.name} (class docstring)",
                file_path=file_path,
                line_start=node.lineno or 0,
            ))

        # Class signature + body (truncated)
        class_source = ast.unparse(node)
        tokens = self.count_tokens(class_source)

        if tokens > 3000:
            class_source = class_source[:12000] + "\n# ... (truncated)"

        chunk_ids.append(self.add(
            content=class_source,
            priority=2,
            chunk_type="class",
            name=node.name,
            file_path=file_path,
            line_start=node.lineno or 0,
            line_end=node.end_lineno or 0,
        ))

        return chunk_ids

    def get_context(
        self,
        query: str = "",
        max_tokens: Optional[int] = None,
        include_types: Optional[list[str]] = None,
        exclude_types: Optional[list[str]] = None,
    ) -> str:
        """
        Get context within token limit, prioritizing by relevance.

        Args:
            query: Query string (currently used for future relevance ranking)
            max_tokens: Override max tokens (default: self.max_tokens)
            include_types: Only include these chunk types
            exclude_types: Exclude these chunk types

        Returns:
            Context string within token limit
        """
        limit = max_tokens or self.max_tokens

        # Filter chunks
        chunks = self._chunks
        if include_types:
            chunks = [c for c in chunks if c.chunk_type in include_types]
        if exclude_types:
            chunks = [c for c in chunks if c.chunk_type not in exclude_types]

        # Sort by priority (descending), then by line number
        chunks = sorted(chunks, key=lambda c: (-c.priority, c.line_start))

        # Build context within limit
        context_parts = []
        current_tokens = 0

        for chunk in chunks:
            if current_tokens + chunk.tokens > limit:
                # Check if we can add partial chunk
                remaining = limit - current_tokens
                if remaining > 200:  # At least 200 tokens to be useful
                    truncated = self._truncate_to_tokens(chunk.content, remaining)
                    context_parts.append(f"# {chunk.file_path}:{chunk.line_start}\n{truncated}")
                    current_tokens = limit
                break

            header = f"# {chunk.file_path}:{chunk.line_start}-{chunk.line_end} ({chunk.chunk_type})"
            if chunk.name:
                header += f" - {chunk.name}"

            context_parts.append(f"{header}\n{chunk.content}")
            current_tokens += chunk.tokens

        return "\n\n".join(context_parts)

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit."""
        if self.encoder:
            tokens = self.encoder.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return cast(str, self.encoder.decode(tokens[:max_tokens]))

        # Fallback: truncate by characters
        approx_chars = max_tokens * 4
        return text[:approx_chars]


    def get_relevant_chunks(
        self,
        query: str,
        k: int = 5,
    ) -> list[Chunk]:
        """
        Get k most relevant chunks for a query.

        Note: This is a simple keyword-based relevance for now.
        For true semantic search, integrate with vector store.

        Args:
            query: Query string
            k: Number of chunks to return

        Returns:
            List of top k relevant chunks
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_chunks = []
        for chunk in self._chunks:
            content_lower = chunk.content.lower()

            # Simple scoring: count query word matches
            score = sum(1 for word in query_words if word in content_lower)

            # Bonus for exact chunk type matches
            if chunk.chunk_type in query_lower:
                score += 2

            # Bonus for name matches
            if chunk.name and chunk.name.lower() in query_lower:
                score += 3

            if score > 0:
                scored_chunks.append((score, chunk))

        # Sort by score, then by priority
        scored_chunks.sort(key=lambda x: (-x[0], -x[1].priority))

        return [chunk for _, chunk in scored_chunks[:k]]

    def summarize(self, text: str, max_tokens: int = 500) -> str:
        """
        Summarize text to fit within token limit.

        For now, this is a simple truncation.
        For true summarization, integrate with LLM.

        Args:
            text: Text to summarize
            max_tokens: Target token count

        Returns:
            Summarized text
        """
        return self._truncate_to_tokens(text, max_tokens)

    def clear(self) -> None:
        """Clear all chunks."""
        self._chunks.clear()
        self._chunk_map.clear()

    @property
    def total_tokens(self) -> int:
        """Get total tokens in current chunks."""
        return sum(c.tokens for c in self._chunks)

    @property
    def total_chunks(self) -> int:
        """Get total number of chunks."""
        return len(self._chunks)

    def get_stats(self) -> dict[str, Any]:
        """Get context manager statistics."""
        type_counts: dict[str, int] = {}
        for chunk in self._chunks:
            type_counts[chunk.chunk_type] = type_counts.get(chunk.chunk_type, 0) + 1

        return {
            "total_chunks": self.total_chunks,
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "utilization_pct": round(self.total_tokens / self.max_tokens * 100, 1),
            "chunks_by_type": type_counts,
            "total_tokens_added": self._total_tokens_added,
            "total_chunks_added": self._total_chunks_added,
            "encoding": _DEFAULT_ENCODING if _HAS_TIKTOKEN else "approximate",
        }


# Singleton instance
_context_manager: Optional[ContextWindowManager] = None


def get_context_manager(max_tokens: int = 128000) -> ContextWindowManager:
    """Get singleton context manager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextWindowManager(max_tokens=max_tokens)
    return _context_manager


__all__ = [
    "Chunk",
    "ContextWindowManager",
    "get_context_manager",
]
