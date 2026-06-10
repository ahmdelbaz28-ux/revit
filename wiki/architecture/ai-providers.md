# AI Provider Integration Architecture

## Overview

FireAI integrates multiple AI providers (OpenAI, Gemini) for advisory-only functions. AI results NEVER override deterministic NFPA 72 calculations. This page documents the architecture, safety constraints, and integration patterns.

## Safety-First Design Principles

1. **AI is ADVISORY, never AUTHORITATIVE** — All AI results are tagged `source="llm_suggestion"`, never `source="nfpa_engine"`
2. **AI failure = empty context** — If any AI provider fails, calculations proceed without AI input
3. **Audit trail** — Every AI interaction is logged for regulatory compliance
4. **PE review gate** — AI suggestions require Professional Engineer approval before implementation
5. **Fail-safe behavior** — AI cannot bypass verification gates

## Current AI Integration

### Memory Service (Mem0)
- **Primary**: OpenAI gpt-4o + text-embedding-3-small (1536 dimensions)
- **Fallback**: Gemini 2.0 Flash + HuggingFace all-MiniLM-L6-v2 (384 dimensions)
- **Storage**: Qdrant vector DB + SQLite history
- **Purpose**: Long-term engineering memory (layout preferences, calculation patterns, device mappings)
- **Safety**: Memory results always carry disclaimer: "ADVISORY CONTEXT only — never overrides NFPA 72 calculations"

### Provider Failover Cascade (5 levels)
1. OpenAI Direct
2. OpenRouter
3. OpenCode Zen/Go
4. Gemini
5. Z.ai proxy (last resort)

## Provider Registry Pattern (from free-claude-code)

FireAI adopts the Provider Registry pattern from the free-claude-code project, adapted for safety-critical engineering:

### Descriptor-Driven Catalog
```python
@dataclass(frozen=True)
class AIProviderDescriptor:
    provider_id: str           # "openai", "gemini"
    transport_type: str        # "openai_chat" | "gemini_native"
    capabilities: tuple        # ("chat", "streaming", "tools")
    credential_env: str        # "OPENAI_API_KEY"
    default_model: str         # "gpt-4o"
    is_primary: bool           # True for primary provider
```

### Dual Transport Strategy
1. **OpenAI-compatible** — Uses OpenAI SDK for streaming, converts to internal format
2. **Gemini-native** — Uses Google AI SDK with Anthropic-compatible response format

### Model Routing by Task
| Task | Model | Rationale |
|------|-------|-----------|
| Safety-critical analysis | gpt-4o | Highest accuracy for engineering calculations |
| Memory extraction | gpt-4o-mini | Cost-effective for metadata extraction |
| Quick classification | gemini-2.0-flash | Fast and free for non-critical tasks |
| Embedding | text-embedding-3-small | 1536 dimensions for semantic search |
| Fallback (quota) | gemini-2.0-flash-lite | Minimal resource usage |

## Integration Points in FireAI

| Module | AI Use Case | Safety Classification |
|--------|-------------|----------------------|
| ConsensusEngine | Multi-model verification of critical calculations | ADVISORY |
| AnalysisPipeline | AI-assisted occupancy classification | ADVISORY + PE review |
| RulesEngine | AI-suggested rules from NFPA 72 text | ADVISORY, must be codified |
| ProofCertificateGenerator | AI-assisted report narrative drafting | ADVISORY, PE signs |
| DigitalTwin | AI anomaly detection in design | ALERT only |
| MemoryService | Long-term engineering memory | ADVISORY (existing) |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API access | None (required) |
| `GEMINI_API_KEY` | Gemini API access | None (fallback) |
| `FIREAI_MEMORY_LLM_PROVIDER` | Memory LLM provider | "openai" |
| `FIREAI_MEMORY_LLM_MODEL` | Memory LLM model | "gpt-4o-mini" |
| `FIREAI_MEMORY_EMBEDDER_PROVIDER` | Embedding provider | "openai" |
| `FIREAI_MEMORY_EMBEDDER_MODEL` | Embedding model | "text-embedding-3-small" |

## Cross-References

- [[architecture/overview|System Architecture Overview]]
- [[architecture/safety-philosophy|Safety-First Design Philosophy]]
- [[decisions/004-ai-safety|Decision 004: AI is ADVISORY Only]]
