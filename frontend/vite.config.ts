// NOSONAR
/// <reference types="vitest" />

import * as path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { mockupPreviewPlugin } from "./mockupPreviewPlugin";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = process.env.PORT ? Number(process.env.PORT) : 5173;
const basePath = process.env.BASE_PATH || "/";

const isTest = process.argv.some((arg) => arg.includes("vitest"));
const isProduction = process.env.NODE_ENV === "production";

// Injects the API URL into the CSP connect-src directive at build time
function cspInjectPlugin(): import("vite").Plugin {
        return {
                name: "csp-inject",
                transformIndexHtml(html) {
                        const apiUrl = process.env.VITE_API_URL || "/api/v1";
                        // V158 FIX (root cause): Previous logic fell back to `origin = apiUrl`
                        // for relative URLs like "/api/v1". This produced an INVALID CSP
                        // `connect-src` entry: "/api/v1" is not a valid CSP source (CSP
                        // requires 'self', 'none', a scheme-host-port tuple, or wildcards).
                        // Browsers log a console error:
                        //   "The source list for the Content Security Policy directive
                        //    'connect-src' contains an invalid source: '/api/v1'. It will be
                        //    ignored."
                        // This caused all 8 Playwright visual smoke tests in
                        // tests/visual/smoke.spec.ts to fail with "Console errors on /<page>".
                        //
                        // Root-cause fix: when apiUrl is a relative URL (no scheme+host),
                        // the CSP already covers it via the 'self' source that is hardcoded
                        // in index.html's connect-src directive. So we emit an EMPTY string
                        // for relative URLs — adding nothing to CSP — which is correct
                        // because relative API calls are same-origin and 'self' covers them.
                        //
                        // For absolute URLs (e.g., "https://api.fireai.example.com"), we
                        // extract the origin and also derive the matching ws/wss origin.
                        let origin = "";
                        let wsOrigin = "";
                        try {
                                const parsed = new URL(apiUrl);
                                // If URL parsing succeeded and we have a protocol + host, it's absolute
                                if (parsed.protocol && parsed.host) {
                                        origin = parsed.origin;
                                        wsOrigin = origin.startsWith("https")
                                                ? origin.replace("https", "wss")
                                                : "";
                                }
                                // Else: leave origin/wsOrigin empty (relative URL — 'self' covers it)
                        } catch {
                                // URL() threw — apiUrl is a relative path like "/api/v1".
                                // Leave origin/wsOrigin empty; 'self' in CSP covers same-origin calls.
                        }
                        const cspConnect = [origin, wsOrigin].filter(Boolean).join(" ");
                        return html.replaceAll("__CSP_CONNECT_SRC__", cspConnect);
                },
        };
}

export default defineConfig({
        base: basePath,
        plugins: [
                mockupPreviewPlugin(),
                react(),
                isTest ? null : tailwindcss(),
                isTest ? null : cspInjectPlugin(),
        ].filter(Boolean),
        resolve: {
                alias: {
                        "@": path.resolve(__dirname, "src"),
                },
        },
        build: {
                outDir: path.resolve(__dirname, "dist"),
                emptyOutDir: true,
                // SECURITY: Disable source maps in production to prevent source code exposure
                sourcemap: !isProduction,
                minify: "terser",
                terserOptions: {
                        // SECURITY: Remove console.log and debugger in production using format options
                        format: {
                                comments: false,
                        },
                        module: true,
                        toplevel: true,
                        // Use compress options compatible with terser
                        compress: {
                                drop_console: isProduction,
                                drop_debugger: true,
                                global_defs: {
                                        "@console.log": isProduction ? "undefined" : "@console.log",
                                },
                        },
                },
                // Code splitting: separate vendor chunks to reduce initial bundle size
                rollupOptions: {
                        output: {
                                manualChunks(id) {
                                        if (
                                                id.includes("node_modules/react/") ||
                                                id.includes("node_modules/react-dom/") ||
                                                id.includes("node_modules/react-router-dom/")
                                        ) {
                                                return "vendor-react";
                                        }
                                        if (id.includes("node_modules/@radix-ui/")) {
                                                return "vendor-ui";
                                        }
                                        if (id.includes("node_modules/@tanstack/")) {
                                                return "vendor-tanstack";
                                        }
                                        if (
                                                id.includes("node_modules/i18next/") ||
                                                id.includes("node_modules/react-i18next/")
                                        ) {
                                                return "vendor-i18n";
                                        }
                                        if (id.includes("node_modules/recharts/")) {
                                                return "vendor-chart";
                                        }
                                        if (id.includes("node_modules/three/")) {
                                                return "vendor-3d";
                                        }
                                },
                        },
                },
                chunkSizeWarningLimit: 600,
        },
        server: {
                port,
                // SECURITY: Bind to localhost only (not 0.0.0.0) to prevent network exposure
                host: process.env.VITE_DEV_HOST || "localhost",
                // SECURITY: Restrict allowed hosts to prevent DNS rebinding attacks
                allowedHosts: process.env.VITE_ALLOWED_HOSTS
                        ? process.env.VITE_ALLOWED_HOSTS.split(",")
                        : ["localhost"],
                // SECURITY: Enable fs.strict to prevent path traversal outside project root
                fs: {
                        strict: true,
                },
                // Security headers for development server
                headers: {
                        "X-Content-Type-Options": "nosniff",
                        "X-Frame-Options": "DENY",
                        "X-XSS-Protection": "1; mode=block",
                        "Referrer-Policy": "strict-origin-when-cross-origin",
                        // V190 FIX: frame-ancestors MUST be delivered via HTTP header (not
                        // <meta>). The <meta> CSP tag is honored for most directives but
                        // NOT for frame-ancestors per CSP3 spec. Set it here so the dev
                        // server enforces clickjacking protection. Production (Vercel/HF
                        // Space) must set the same header via their config.
                        "Content-Security-Policy-Frame-Ancestors": "'none'",
                },
                proxy: {
                        "/api": {
                                target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
                                changeOrigin: true,
                        },
                        "/ws": {
                                target: process.env.VITE_API_PROXY_TARGET || "ws://localhost:8000",
                                ws: true,
                        },
                },
        },
        preview: {
                port,
                host: "localhost",
                allowedHosts: ["localhost"],
        },
        ...(isTest
                ? {
                                test: {
                                        globals: true,
                                        environment: "jsdom",
                                        setupFiles: ["./src/test/setup.ts"],
                                        css: true,
                                        // V156 FIX: Exclude Playwright visual tests from Vitest collection.
                                        // tests/visual/*.spec.ts are Playwright test files (use @playwright/test's
                                        // test() function). When Vitest discovers them, it fails with:
                                        //   "Playwright Test did not expect test() to be called here"
                                        // because Playwright's test() is not the same as Vitest's test().
                                        // These tests must be run with `npx playwright test`, not `npx vitest`.
                                        // Excluding them here makes `npm run test` (Vitest) pass 100%.
                                        exclude: [
                                                "**/node_modules/**",
                                                "**/dist/**",
                                                "**/cypress/**",
                                                "**/.{idea,git,cache,output,temp}/**",
                                                "**/{karma,rollup,webpack,vite,vitest,jest,ava,babel,nyc,cypress,tsup,build}.config.*",
                                                "tests/**",
                                        ],
                                },
                        }
                : {}),
});
