"""
code_rag.py — Code RAG (Retrieval-Augmented Generation) for Code Understanding
============================================================================

Provides RAG-based code understanding using:
1. Context Window Management (token counting, chunking)
2. Vector Search (semantic code search)
3. Modal API (GLM-5-FP8 for generation)

Features:
- Natural language queries about code
- Automatic context retrieval
- Code-aware prompts
- Conversation history

Usage:
    from fireai.infrastructure.code_rag import CodeRAG

    rag = CodeRAG()
    rag.index_directory("fireai")

    response = rag.query("How does the vector store work?")
    print(response)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from fireai.infrastructure.code_indexer import CodeIndexer
from fireai.infrastructure.context_window_manager import ContextWindowManager

logger = logging.getLogger(__name__)


# Modal API Configuration
MODAL_API_URL = "https://api.us-west-2.modal.direct/v1/chat/completions"
DEFAULT_MODEL = "zai-org/GLM-5-FP8"
DEFAULT_MAX_TOKENS = 1000
DEFAULT_CONTEXT_TOKENS = 32000  # Leave room for response


@dataclass
class RAGConfig:
    """Configuration for Code RAG."""
    modal_api_url: str = MODAL_API_URL
    modal_api_key: str = ""
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    context_max_tokens: int = DEFAULT_CONTEXT_TOKENS
    retrieval_k: int = 10
    temperature: float = 0.1
    system_prompt: str = """You are a helpful AI assistant specialized in code analysis.
You help users understand codebases, find relevant code, and answer questions about software.
Always be concise and accurate. When showing code, use proper formatting."""

    def __post_init__(self) -> None:
        if not self.modal_api_key:
            # Try to get from environment
            self.modal_api_key = os.environ.get(
                "MODAL_RESEARCH_KEY",
                "modalresearch_TzUJFpXlhpM9zxRhymgDm4DZmIT_IFDGYuPtZT9Eekg"
            )


class CodeRAG:
    """
    Code RAG - Retrieval-Augmented Generation for Code Understanding.

    Combines:
    1. CodeIndexer (for indexing and retrieval)
    2. ContextWindowManager (for context management)
    3. Modal API (for generation)

    Args:
        config: RAG configuration
        index_root: Root directory to index
    """

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        index_root: str = ".",
    ):
        self.config = config or RAGConfig()

        # Initialize components
        self.indexer = CodeIndexer(root_dir=index_root)
        self.context_manager = ContextWindowManager(
            max_tokens=self.config.context_max_tokens
        )

        # Conversation history
        self._history: list[dict[str, str]] = []

    def index_directory(self, directory: Path) -> dict[str, Any]:
        """
        Index a directory for retrieval.

        Args:
            directory: Directory path to index

        Returns:
            Index statistics
        """
        return self.indexer.index_directory(directory)

    def index_all(self) -> dict[str, Any]:
        """
        Index all Python files in the root directory.

        Returns:
            Index statistics
        """
        return self.indexer.index_all()

    def _build_context(self, query: str) -> str:
        """
        Build context from relevant code chunks.

        Args:
            query: User query

        Returns:
            Context string
        """
        # Search for relevant chunks
        results = self.indexer.search(query, k=self.config.retrieval_k)

        if not results:
            return "No relevant code found."

        # Add to context manager
        self.context_manager.clear()

        for result in results:
            self.context_manager.add(
                content=result["content"],
                priority=2,
                chunk_type=result["metadata"].get("type", "text"),
                name=result["metadata"].get("name", ""),
                file_path=result["metadata"].get("file_path", ""),
                line_start=result["metadata"].get("line_start", 0),
                line_end=result["metadata"].get("line_end", 0),
            )

        # Get context within token limit
        return self.context_manager.get_context(
            max_tokens=self.config.context_max_tokens
        )

    def _call_modal(self, messages: list[dict[str, str]], retries: int = 3) -> str:
        """
        Call Modal API for generation with retry logic.

        Args:
            messages: Chat messages
            retries: Number of retries on rate limit

        Returns:
            Generated response
        """
        import time

        headers = {
            "Authorization": f"Bearer {self.config.modal_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        for attempt in range(retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(
                        self.config.modal_api_url,
                        headers=headers,
                        json=payload,
                    )

                if response.status_code == 200:
                    data = response.json()
                    return str(data["choices"][0]["message"]["content"])
                elif response.status_code == 429:
                    if attempt < retries - 1:
                        wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                        logger.warning(f"Rate limited. Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    return "Too many requests. Please wait a moment and try again."
                else:
                    logger.error(f"Modal API error: {response.status_code} - {response.text}")
                    return f"API error: {response.status_code}"

            except Exception as e:
                logger.error(f"Modal API call failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return f"Request failed: {e}"

        return "Failed after retries."

    def query(
        self,
        question: str,
        include_history: bool = True,
    ) -> str:
        """
        Query the code with a natural language question.

        Args:
            question: User question
            include_history: Whether to include conversation history

        Returns:
            Generated answer
        """
        # Build context
        context = self._build_context(question)

        # Build messages
        messages = [
            {"role": "system", "content": self.config.system_prompt},
        ]

        # Add history if requested
        if include_history and self._history:
            for h in self._history[-5:]:  # Last 5 exchanges
                messages.append({"role": "user", "content": h["question"]})
                messages.append({"role": "assistant", "content": h["answer"]})

        # Add context and question
        context_prompt = f"""Based on the following code context, answer the question.

Context:
{context}

Question: {question}

Answer:"""

        messages.append({"role": "user", "content": context_prompt})

        # Get response
        response = self._call_modal(messages)

        # Update history
        self._history.append({
            "question": question,
            "answer": response,
        })

        return response

    def query_code_location(
        self,
        feature: str,
    ) -> str:
        """
        Find where a feature/function/class is defined.

        Args:
            feature: Feature name to find

        Returns:
            Location and relevant code
        """
        results = self.indexer.search(feature, k=5)

        if not results:
            return f"No code found for '{feature}'."

        locations = []
        for r in results:
            meta = r["metadata"]
            loc = f"- **{meta.get('name', 'unknown')}** ({meta.get('type', 'text')})\n"
            loc += f"  File: `{meta.get('file_path', 'unknown')}`"
            if meta.get('line_start'):
                loc += f":{meta['line_start']}"
            locations.append(loc)

        return f"Found {len(results)} matches:\n\n" + "\n\n".join(locations)

    def query_code_explanation(
        self,
        file_path: str,
    ) -> str:
        """
        Get explanation of a file's code.

        Args:
            file_path: Path to the file

        Returns:
            Explanation
        """
        # Get all chunks from file
        chunks = self.indexer.search_by_file(file_path)

        if not chunks:
            return f"No code found in '{file_path}'."

        # Combine chunks
        content = "\n\n".join([
            f"## {c['metadata'].get('name', 'Unknown')} ({c['metadata'].get('type', 'text')})\n{c['content']}"
            for c in chunks[:10]  # Limit to 10 chunks
        ])

        prompt = f"""Explain the following code:

```{content}
```

Provide a summary of what this code does and its main components."""

        messages = [
            {"role": "system", "content": "You are a helpful code analysis assistant."},
            {"role": "user", "content": prompt},
        ]

        return self._call_modal(messages)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()

    def clear_index(self) -> None:
        """Clear the code index."""
        self.indexer.clear()
        self.context_manager.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get RAG statistics."""
        return {
            "indexer": self.indexer.get_stats(),
            "context_tokens": self.context_manager.total_tokens,
            "history_length": len(self._history),
        }


# Singleton
_rag: Optional[CodeRAG] = None


def get_code_rag(index_root: str = ".") -> CodeRAG:
    """Get singleton CodeRAG instance."""
    global _rag
    if _rag is None:
        _rag = CodeRAG(index_root=index_root)
    return _rag


__all__ = [
    "CodeRAG",
    "RAGConfig",
    "get_code_rag",
]
