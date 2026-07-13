
import * as Sentry from "@sentry/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ErrorRecovery } from "./components/core/ErrorRecovery";
import "@/utils/fontLoader";
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
                integrations: [Sentry.browserTracingIntegration()],
                ignoreErrors: [
                        "ResizeObserver loop limit exceeded",
                        "NetworkError when attempting to fetch resource",
                ],
        });
}

// ── Root Element Guard ────────────────────────────────────────────────────
const rootEl = document.getElementById("root");
if (!rootEl) {
        throw new Error(
                "BAZSPARK: Root element #root not found in DOM. Cannot mount application.",
        );
}

// V250 FIX: ChunkLoadError handler — when a stale deployment causes a
// chunk to fail loading (404 on /assets/index-OLD_HASH.js), automatically
// reload the page ONCE to pick up the new chunks. Without this, users see
// a full-screen error view and must manually reload.
let chunkErrorReloadAttempted = false;
window.addEventListener("error", (event) => {
        // Check for chunk load errors (Vite lazy-loaded chunks)
        const isChunkError =
                event.error?.name === "ChunkLoadError" ||
                (event.error?.message?.includes("Failed to fetch dynamically imported module") ?? false) ||
                (event.error?.message?.includes("Loading chunk") ?? false);
        if (isChunkError && !chunkErrorReloadAttempted) {
                chunkErrorReloadAttempted = true;
                console.warn("[BAZSPARK] Chunk load failed — reloading to pick up new deployment...");
                window.location.reload();
        }
});

createRoot(rootEl).render(
        <BrowserRouter basename={import.meta.env.BASE_URL || "/"}>
                <QueryClientProvider client={queryClient}>
                        <ErrorRecovery
                                onError={(error, info) =>
                                        console.error(
                                                "[BAZSPARK] Fatal error caught by boundary:",
                                                error,
                                                info,
                                        )
                                }
                        >
                                <App />
                        </ErrorRecovery>
                </QueryClientProvider>
        </BrowserRouter>,
);
