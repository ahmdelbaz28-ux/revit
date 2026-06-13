/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { fileURLToPath } from "url";
import { mockupPreviewPlugin } from "./mockupPreviewPlugin";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = process.env.PORT ? Number(process.env.PORT) : 5173;
const basePath = process.env.BASE_PATH || "/";

const isTest = process.argv.some(arg => arg.includes("vitest"));
const isProduction = process.env.NODE_ENV === "production";

export default defineConfig({
  base: basePath,
  plugins: [
    mockupPreviewPlugin(),
    react(),
    !isTest ? tailwindcss() : null,
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
      compress: {
        // SECURITY: Remove console.log and debugger in production
        drop_console: isProduction,
        drop_debugger: true,
      },
    },
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
    },
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
  preview: {
    port,
    host: "localhost",
    allowedHosts: ["localhost"],
  },
  ...(isTest ? {
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: true,
    },
  } : {}),
});
