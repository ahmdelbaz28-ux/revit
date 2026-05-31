import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Sentry from "@sentry/react";
import React from "react";
import App from "./App";
import "./index.css";

// ── React Query Client ────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// ── Sentry Error Tracking ─────────────────────────────────────────────────
const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    release: `fireai-digital-twin@${import.meta.env.VITE_APP_VERSION || "1.0.0"}`,
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 1.0,
    integrations: [
      Sentry.browserTracingIntegration(),
    ],
    ignoreErrors: [
      "ResizeObserver loop limit exceeded",
      "NetworkError when attempting to fetch resource",
    ],
  });
}

// ── Error Boundary Fallback ───────────────────────────────────────────────
// Safety-critical: prevents white-screen crashes that would disable
// the fire alarm engineering interface. If Sentry is configured,
// errors are automatically reported.
class ErrorBoundaryFallback extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  state = { hasError: false, error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[FireAI] Fatal error caught by boundary:", error, errorInfo);
    // If Sentry is configured, the integration already captures this
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: '#0f172a',
          color: '#e2e8f0',
          fontFamily: 'Inter, system-ui, sans-serif',
          padding: '2rem',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔥</div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>
            FireAI encountered an error
          </h1>
          <p style={{ color: '#94a3b8', marginBottom: '1.5rem', maxWidth: '400px' }}>
            The application encountered an unexpected error. Your project data is safe.
            Please reload the application to continue.
          </p>
          <details style={{ marginBottom: '1.5rem', maxWidth: '600px', width: '100%', textAlign: 'left' }}>
            <summary style={{ cursor: 'pointer', color: '#64748b', fontSize: '0.875rem' }}>
              Error details
            </summary>
            <pre style={{
              marginTop: '0.5rem',
              padding: '1rem',
              backgroundColor: '#1e293b',
              borderRadius: '0.5rem',
              overflow: 'auto',
              fontSize: '0.75rem',
              color: '#f87171',
            }}>
              {this.state.error?.message || 'Unknown error'}
            </pre>
          </details>
          <button
            onClick={this.handleReload}
            style={{
              padding: '0.625rem 1.5rem',
              backgroundColor: '#ea580c',
              color: 'white',
              border: 'none',
              borderRadius: '0.5rem',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Root Element Guard ────────────────────────────────────────────────────
const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("FireAI: Root element #root not found in DOM. Cannot mount application.");
}

createRoot(rootEl).render(
  <BrowserRouter basename={import.meta.env.BASE_URL || '/'}>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundaryFallback>
        <App />
      </ErrorBoundaryFallback>
    </QueryClientProvider>
  </BrowserRouter>
);
