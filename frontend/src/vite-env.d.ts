/// <reference types="vite/client" />

interface ImportMetaEnv {
	// API connection
	readonly VITE_API_URL: string;
	readonly VITE_WS_URL: string;

	// App identity
	readonly VITE_APP_NAME: string;
	readonly VITE_APP_VERSION: string;

	// Authentication (NEVER put real secrets here — visible in bundle)
	readonly VITE_FIREAI_API_KEY: string;

	// Error tracking (optional)
	readonly VITE_SENTRY_DSN: string;

	// Vite builtins
	readonly BASE_URL: string;
	readonly MODE: string;
	readonly DEV: boolean;
	readonly PROD: boolean;
	readonly SSR: boolean;
}

interface ImportMeta {
	readonly env: ImportMetaEnv;
}
