import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";
// Explicit import required: tsconfig.json `types: ["node", "vite/client"]` does not
// include `vitest/globals`, so vitest's `globals: true` is invisible to tsc.
// This fixes CI Build Gate TS2304 ("Cannot find name 'afterEach'").
import { afterEach } from "vitest";

// Use vitest globals directly (globals: true in vitest config)
afterEach(() => {
	cleanup();
});
