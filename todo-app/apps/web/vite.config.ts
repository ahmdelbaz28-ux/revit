// NOSONAR
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [react()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
	server: {
		port: 5173,
		proxy: {
			"/auth": "http://localhost:3001",
			"/tasks": "http://localhost:3001",
			"/health": "http://localhost:3001",
		},
	},
});
