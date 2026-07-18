import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";

// Use vitest globals directly (globals: true in vitest config)
afterEach(() => {
	cleanup();
});
