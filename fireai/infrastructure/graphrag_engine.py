"""
graphrag_engine.py — GraphRAG Engine: Semantic Vector Memory + Knowledge Graph
================================================================================

V142: Combines Qdrant/Neo4j vector search with Neo4j knowledge graph traversal
to give AI agents TRUE understanding — not just text similarity, but relational
reasoning ("Sami works in Dhahran because Sami → WORKS_AT → Aramco → LOCATED_IN → Dhahran").

Architecture (3 layers):
1. **Vector Store Layer**: Neo4jVector — stores text chunks as embeddings (1536d OpenAI)
   - Semantic search: "find text similar to this query"
   - Index: ai_memory_index (cosine similarity)

2. **Knowledge Graph Layer**: LLMGraphTransformer — extracts entities + relationships
   - Nodes: Person, Organization, Location, Technology, Standard, Project
   - Relationships: WORKS_AT, LOCATED_IN, USES, RELATED_TO, MENTIONS
   - LLM (GPT-4o) reads text and decides what entities/relationships to create

3. **Hybrid Retrieval Layer**: GraphCypherQAChain — writes Cypher queries to answer
   - Given a question, the LLM generates a Cypher query
   - Neo4j executes the query (graph traversal)
   - LLM formulates a natural language answer from the results

Safety (per agent.md Rule 12):
- GraphRAG is ADVISORY ONLY — it never overrides deterministic calculations
- All data is traceable (Neo4j Browser shows the full knowledge graph visually)
- Falls back gracefully when Neo4j or OpenAI unavailable

Usage:
    from fireai.infrastructure.graphrag_engine import GraphRAGEngine

    engine = GraphRAGEngine()

    # Store knowledge (vector + graph)
    engine.add_knowledge("Ahmed works at Aramco as a fire protection engineer.")

    # Ask questions (hybrid retrieval)
    answer = engine.ask("Where does Ahmed work?")
    # → "Ahmed works at Aramco as a fire protection engineer."

References:
- Neo4j GraphRAG: https://neo4j.com/labs/genai-ecosystem/langchain/
- LangChain Neo4j: https://python.langchain.com/docs/integrations/graphs/neo4j_cypher
- agent.md Rule 12 (Safety-First): AI memory is ADVISORY only
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GraphRAGEngine:
    """
    GraphRAG Engine: Hybrid Vector + Graph retrieval for AI agents.

    Combines 3 layers:
    1. Neo4jVector (semantic text search)
    2. LLMGraphTransformer (entity/relationship extraction)
    3. GraphCypherQAChain (natural language → Cypher → answer)

    All layers use Neo4j Aura as the unified backend (vector + graph in one DB).
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int = 1536,
        llm_model: str = "gpt-4o",
    ) -> None:
        """
        Initialize the GraphRAG engine.

        Args:
            neo4j_uri: Neo4j connection URI (bolt:// or neo4j+s://).
            neo4j_user: Neo4j username.
            neo4j_password: Neo4j password.
            openai_api_key: OpenAI API key for embeddings + LLM.
            embedding_model: OpenAI embedding model name.
            embedding_dimensions: Embedding vector dimensions (must match model).
            llm_model: OpenAI LLM model for graph transformation + QA.
        """
        self._neo4j_uri = neo4j_uri or os.environ.get("NEO4J_URI", "")
        self._neo4j_user = neo4j_user or os.environ.get("NEO4J_USER", "neo4j")
        self._neo4j_password = neo4j_password or os.environ.get("NEO4J_PASSWORD", "")
        self._openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._llm_model = llm_model

        self._graph = None        # Neo4jGraph connection
        self._vector_store = None  # Neo4jVector store
        self._transformer = None   # LLMGraphTransformer
        self._qa_chain = None      # GraphCypherQAChain
        self._initialized = False

    def _initialize(self) -> None:
        """Initialize all 3 layers (lazy, with graceful fallback)."""
        if self._initialized:
            return

        if not self._neo4j_uri or not self._neo4j_password:
            logger.warning("GraphRAG: Neo4j credentials not configured. Engine disabled.")
            self._initialized = True
            return

        if not self._openai_key:
            logger.warning("GraphRAG: OPENAI_API_KEY not set. Engine disabled (no embeddings/LLM).")
            self._initialized = True
            return

        try:
            # Set env vars for LangChain (it reads from os.environ)
            os.environ["NEO4J_URI"] = self._neo4j_uri
            os.environ["NEO4J_USERNAME"] = self._neo4j_user
            os.environ["NEO4J_PASSWORD"] = self._neo4j_password
            os.environ["OPENAI_API_KEY"] = self._openai_key

            # Layer 1: Neo4jGraph connection (for graph operations)
            from langchain_neo4j import Neo4jGraph

            self._graph = Neo4jGraph(
                url=self._neo4j_uri,
                username=self._neo4j_user,
                password=self._neo4j_password,
            )
            logger.info("GraphRAG: Neo4jGraph connected to %s", self._neo4j_uri)

            # Layer 2: Neo4jVector (semantic vector store)
            from langchain_neo4j import Neo4jVector
            from langchain_openai import OpenAIEmbeddings

            embeddings = OpenAIEmbeddings(model=self._embedding_model)

            try:
                # Try to connect to existing index
                self._vector_store = Neo4jVector.from_existing_index(
                    embeddings,
                    index_name="ai_memory_index",
                    node_label="MemoryChunk",
                    text_node_property="text",
                    embedding_node_property="embedding",
                )
                logger.info("GraphRAG: Connected to existing vector index 'ai_memory_index'")
            except Exception:
                # Create new index if it doesn't exist
                self._vector_store = Neo4jVector.from_existing_graph(
                    embeddings,
                    index_name="ai_memory_index",
                    node_label="MemoryChunk",
                    text_node_properties=["text"],
                    embedding_node_property="embedding",
                )
                logger.info("GraphRAG: Created new vector index 'ai_memory_index'")

            # Layer 3: LLMGraphTransformer (entity/relationship extraction)
            from langchain_experimental.graph_transformers import LLMGraphTransformer
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model=self._llm_model, temperature=0)
            self._transformer = LLMGraphTransformer(llm=llm)
            logger.info("GraphRAG: LLMGraphTransformer initialized (model=%s)", self._llm_model)

            # Layer 4: GraphCypherQAChain (natural language → Cypher → answer)
            from langchain_neo4j import GraphCypherQAChain

            self._qa_chain = GraphCypherQAChain.from_llm(
                llm=ChatOpenAI(model=self._llm_model, temperature=0),
                graph=self._graph,
                verbose=False,
            )
            logger.info("GraphRAG: GraphCypherQAChain initialized")

        except ImportError as exc:
            logger.warning(
                "GraphRAG: Missing dependency (%s). Install: pip install langchain-neo4j langchain-experimental langchain-openai",
                exc,
            )
        except Exception as exc:
            logger.warning("GraphRAG initialization failed: %s", exc, exc_info=True)

        self._initialized = True

    # ------------------------------------------------------------------
    # Layer 1+2: Store text as vector (semantic search)
    # ------------------------------------------------------------------

    def save_to_memory(self, text: str) -> bool:
        """
        Store a text chunk in the vector store for semantic search.

        Args:
            text: Text to store (will be embedded and indexed).

        Returns:
            True if stored, False if failed.
        """
        self._initialize()
        if self._vector_store is None:
            logger.warning("GraphRAG: Vector store not available — text not stored")
            return False

        try:
            self._vector_store.add_texts([text])
            logger.info("GraphRAG: Stored text chunk (%d chars)", len(text))
            return True
        except Exception as exc:
            logger.error("GraphRAG: Failed to store text: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Layer 2: Store knowledge as graph (entity/relationship extraction)
    # ------------------------------------------------------------------

    def add_knowledge(self, text: str) -> bool:
        """
        Analyze text, extract entities + relationships, store as knowledge graph.

        Uses LLMGraphTransformer to:
        1. Read the text
        2. Identify entities (Person, Organization, Location, etc.)
        3. Identify relationships between entities
        4. Store as Neo4j nodes + edges

        Also stores the original text as a vector for semantic search.

        Args:
            text: Text to analyze and store.

        Returns:
            True if stored, False if failed.
        """
        self._initialize()
        if self._transformer is None or self._graph is None:
            logger.warning("GraphRAG: Transformer/graph not available — knowledge not added")
            return False

        try:
            from langchain_core.documents import Document

            docs = [Document(page_content=text)]
            graph_documents = self._transformer.convert_to_graph_documents(docs)
            self._graph.add_graph_documents(graph_documents)

            # Also store as vector for semantic search
            if self._vector_store is not None:
                self._vector_store.add_texts([text])

            n_nodes = sum(len(gd.nodes) for gd in graph_documents) if graph_documents else 0
            n_rels = sum(len(gd.relationships) for gd in graph_documents) if graph_documents else 0
            logger.info(
                "GraphRAG: Added knowledge (%d entities, %d relationships)",
                n_nodes, n_rels,
            )
            return True

        except Exception as exc:
            logger.error("GraphRAG: Failed to add knowledge: %s", exc, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Layer 3: Hybrid retrieval (vector + graph)
    # ------------------------------------------------------------------

    def ask(self, question: str) -> str:
        """
        Ask a question using hybrid retrieval (vector + graph).

        The GraphCypherQAChain will:
        1. Generate a Cypher query from the natural language question
        2. Execute the query on Neo4j (graph traversal)
        3. Formulate a natural language answer from the results

        Args:
            question: Natural language question.

        Returns:
            Answer string, or error message if failed.
        """
        self._initialize()
        if self._qa_chain is None:
            return "GraphRAG engine not available (Neo4j or OpenAI not configured)."

        try:
            result = self._qa_chain.invoke({"query": question})
            # GraphCypherQAChain returns {"result": "...", "query": "..."}
            if isinstance(result, dict):
                return result.get("result", str(result))
            return str(result)
        except Exception as exc:
            logger.error("GraphRAG: Query failed: %s", exc, exc_info=True)
            return f"GraphRAG query failed: {exc}"

    # ------------------------------------------------------------------
    # Semantic search (vector only, no LLM)
    # ------------------------------------------------------------------

    def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar text chunks using vector similarity.

        Args:
            query: Search query.
            limit: Max results.

        Returns:
            List of {"text": ..., "score": ...} dicts.
        """
        self._initialize()
        if self._vector_store is None:
            return []

        try:
            docs = self._vector_store.similarity_search_with_score(query, k=limit)
            return [
                {"text": doc.page_content, "score": round(score, 4)}
                for doc, score in docs
            ]
        except Exception as exc:
            logger.error("GraphRAG: Search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Check GraphRAG engine health."""
        self._initialize()
        return {
            "initialized": self._initialized,
            "neo4j_connected": self._graph is not None,
            "vector_store": self._vector_store is not None,
            "transformer": self._transformer is not None,
            "qa_chain": self._qa_chain is not None,
            "embedding_model": self._embedding_model,
            "embedding_dimensions": self._embedding_dimensions,
            "llm_model": self._llm_model,
            "neo4j_uri": self._neo4j_uri[:30] + "..." if self._neo4j_uri else "not set",
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_graphrag_engine: Optional[GraphRAGEngine] = None


def get_graphrag_engine() -> GraphRAGEngine:
    """Get the singleton GraphRAGEngine instance."""
    global _graphrag_engine
    if _graphrag_engine is None:
        _graphrag_engine = GraphRAGEngine()
    return _graphrag_engine


__all__ = [
    "GraphRAGEngine",
    "get_graphrag_engine",
]
