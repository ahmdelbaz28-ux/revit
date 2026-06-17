import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Sentry from "@sentry/react";
import App from "./App";
import { ErrorRecovery } from "./components/core/ErrorRecovery";
import "./i18n";
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
    // SECURITY: Limit replay capture rate to 10% to reduce risk of
    // capturing sensitive engineering data (fire alarm designs, building plans)
    // in Sentry session replays. Full 1.0 rate could expose PII/building data.
    replaysOnErrorSampleRate: 0.1,
    integrations: [
      Sentry.browserTracingIntegration(),
    ],
    ignoreErrors: [
      "ResizeObserver loop limit exceeded",
      "NetworkError when attempting to fetch resource",
    ],
  });
}

// ── Root Element Guard ────────────────────────────────────────────────────
const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("FireAI: Root element #root not found in DOM. Cannot mount application.");
}

createRoot(rootEl).render(
  <BrowserRouter basename={import.meta.env.BASE_URL || '/'}>
    <QueryClientProvider client={queryClient}>
      <ErrorRecovery onError={(error, info) => console.error("[FireAI] Fatal error caught by boundary:", error, info)}>
        <App />
      </ErrorRecovery>
    </QueryClientProvider>
  </BrowserRouter>
);
