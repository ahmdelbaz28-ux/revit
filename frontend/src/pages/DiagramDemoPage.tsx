/**
 * DiagramDemoPage — Demonstrates the MermaidRenderer with various diagram types.
 * ==========================================================================
 *
 * This page serves two purposes:
 *   1. Manual QA: engineers can visually verify diagrams render correctly
 *   2. Integration test target: tests verify the page mounts without errors
 *
 * Diagram types tested:
 *   - Flowchart (graph TD/LR)
 *   - Sequence diagram
 *   - ER diagram
 *   - State diagram
 *   - Class diagram
 *   - FireAI-specific: ML subsystem architecture
 */

import React, { useState } from 'react';
import { MermaidRenderer } from '@/components/diagrams/MermaidRenderer';

const DIAGRAMS: { id: string; label: string; code: string }[] = [
  {
    id: 'flowchart',
    label: 'Flowchart (TD)',
    code: `graph TD
    A[Start] --> B{Is NFPA 72 compliant?}
    B -->|Yes| C[Approve Design]
    B -->|No| D[Flag Violations]
    D --> E[Engineer Review]
    E --> A
    C --> F[Deploy to BIM]`,
  },
  {
    id: 'flowchart-lr',
    label: 'Flowchart (LR)',
    code: `graph LR
    A[DWG File] --> B[Parser]
    B --> C[Digital Twin Engine]
    C --> D[RVT Export]
    C --> E[Compliance Check]
    E --> F[Audit Trail]`,
  },
  {
    id: 'sequence',
    label: 'Sequence Diagram',
    code: `sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant ML as ML Subsystem
    participant DB as Audit DB

    U->>API: POST /api/v1/ml/predict
    API->>ML: predict(asset)
    ML->>ML: Run XGBoost + Cox PH
    ML->>ML: Generate SHAP explanation
    ML-->>API: MLPredictionResponse
    API->>DB: Write audit entry
    API-->>U: 200 OK + audit_trail_id`,
  },
  {
    id: 'er',
    label: 'ER Diagram',
    code: `erDiagram
    ASSET ||--o{ MAINTENANCE_EVENT : "has"
    ASSET ||--o{ FAILURE_PREDICTION : "predicts"
    MAINTENANCE_EVENT ||--|| AUDIT_ENTRY : "logs"
    FAILURE_PREDICTION ||--|| SHAP_EXPLANATION : "explains"
    ASSET {
      string asset_id PK
      string asset_type
      date installation_date
      string environment
    }
    FAILURE_PREDICTION {
      string prediction_id PK
      string asset_id FK
      float failure_probability
      string risk_level
    }`,
  },
  {
    id: 'state',
    label: 'State Diagram',
    code: `stateDiagram-v2
    [*] --> Pending
    Pending --> Processing : predict() called
    Processing --> Completed : success
    Processing --> Failed : exception
    Completed --> [*]
    Failed --> Pending : retry
    Completed --> Archived : 30 days elapsed
    Archived --> [*]`,
  },
  {
    id: 'ml-architecture',
    label: 'FireAI ML Architecture',
    code: `graph TD
    subgraph "Frontend"
      UI[PredictiveMaintenancePage]
      UI --> |POST /predict| API[FastAPI Router]
    end

    subgraph "Backend - fireai/ml/"
      API --> Predictor[MLFailurePredictor]
      Predictor --> |ensemble| XGB[XGBoost Model]
      Predictor --> |ensemble| COX[Cox PH Model]
      Predictor --> |ensemble| LSTM[LSTM Model]
      XGB --> |SHAP| Explainer[SHAP Explainer]
      COX --> |HR| Explainer
      LSTM --> |ablation| Explainer
    end

    subgraph "Safety Layer"
      Predictor --> |advisory_only| Contract[enforcement_contract]
      API --> |write| Audit[Audit Trail JSON]
      API --> |RBAC check| RBAC[ApiKeyMiddleware]
    end

    subgraph "Deterministic (Authoritative)"
      Stat[fireai/analytics/<br/>predictive_maintenance.py]
      Stat --> |Weibull baseline| Predictor
    end

    Audit --> NFPA72[NFPA 72 §14.4 compliance]`,
  },
];

export const DiagramDemoPage: React.FC = () => {
  const [selectedId, setSelectedId] = useState(DIAGRAMS[0].id);
  const selected = DIAGRAMS.find((d) => d.id === selectedId) ?? DIAGRAMS[0];

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <h1 className="text-2xl font-bold">Mermaid Diagram Demo</h1>
          <p className="mt-1 text-sm text-slate-400">
            Visual QA page for the MermaidRenderer component. Adapted from{' '}
            <a
              href="https://github.com/TemRevil/Kittle"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-400 underline"
            >
              Kittle
            </a>{' '}
            (MIT-style license).
          </p>
        </header>

        <nav className="flex flex-wrap gap-2" aria-label="Diagram selector">
          {DIAGRAMS.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                selectedId === d.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
              aria-pressed={selectedId === d.id}
            >
              {d.label}
            </button>
          ))}
        </nav>

        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">Source code:</h2>
          <pre className="max-h-48 overflow-auto rounded-lg bg-slate-900 p-4 text-xs text-slate-300">
            <code>{selected.code}</code>
          </pre>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">Rendered diagram:</h2>
          <MermaidRenderer code={selected.code} />
        </section>

        <footer className="border-t border-slate-800 pt-4 text-xs text-slate-500">
          <p>
            <strong>Security note:</strong> MermaidRenderer uses{' '}
            <code>securityLevel: 'loose'</code> for interactive diagrams. This is safe
            because we only render trusted diagram code (engineer-authored or generated
            by FireAI's LLM subsystem), never user-submitted HTML.
          </p>
        </footer>
      </div>
    </div>
  );
};

export default DiagramDemoPage;
