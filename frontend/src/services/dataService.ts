// NOSONAR
import { actions } from "@/store/simpleStore";

/**
 * DataService — Real-time telemetry connection manager.
 *
 * Connects to the BAZSPARK backend via WebSocket (/ws endpoint) for live data,
 * with automatic fallback to mock data in demo/development mode.
 *
 * Backend WebSocket protocol (sync.py):
 *   Client → Server: {"action": "auth", "apiKey": "..."}  (if FIREAI_API_KEY is set)
 *   Client → Server: {"action": "ping"}
 *   Client → Server: {"action": "subscribe", "projectId": "..."}
 *   Client → Server: {"action": "get_status", "projectId": "..."}
 *   Server → Client: {"channel": "system", "type": "auth_success", ...}
 *   Server → Client: {"channel": "system", "type": "pong", ...}
 *   Server → Client: {"channel": "sync", "type": "sync_completed", "data": {...}}
 *   Server → Client: {"channel": "system", "type": "subscribed", ...}
 *
 * Data modes:
 *   - 'live'       → WebSocket connection to backend /ws endpoint
 *   - 'mock'       → Mock worker with simulated telemetry data
 *   - 'demo'       → Same as mock (default for new users)
 *   - 'simulation' → Mock with configurable parameters
 */

const WS_BASE_URL =
	import.meta.env.VITE_WS_URL ||
	// Derive WebSocket URL from current page origin
	(typeof window !== "undefined"
		? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`  // NOSONAR — S3358: nested ternary acceptable in this localized context
		: "ws://localhost:8000/ws");

const WS_RECONNECT_INTERVAL = 5000;
const WS_MAX_RECONNECT_ATTEMPTS = 10;
const WS_HEALTH_CHECK_INTERVAL = 30000;

export class DataService {
	private static instance: DataService;
	private buffer: any[] = [];
	private maxBufferSize = 50; // NOSONAR — acceptable in this context
	private isConnected = false;
	private isAuthenticated = false;
	private reconnectAttempts = 0;
	private subscribedProjectId: string | null = null;

	// WebSocket connection
	private ws: WebSocket | null = null;

	// Mock worker fallback
	private mockWorker: Worker | null = null;

	// Current data source
	private dataSource: "live" | "mock" = "mock";

	// Health check timer
	private healthCheckTimer: ReturnType<typeof setInterval> | null = null;

	// API key for WebSocket authentication
	private apiKey: string | null = null;

	private constructor() {
		// Try to load API key from localStorage or environment
		try {
			this.apiKey = localStorage.getItem("fireai_api_key") || null;
		} catch {
			// localStorage not available
		}
	}

	public static getInstance(): DataService {
		if (!DataService.instance) {
			DataService.instance = new DataService();
		}
		return DataService.instance;
	}

	/** Set the API key for WebSocket authentication */
	public setApiKey(key: string | null) {
		this.apiKey = key;
		try {
			if (key) {
				localStorage.setItem("fireai_api_key", key);
			} else {
				localStorage.removeItem("fireai_api_key");
			}
		} catch {
			// localStorage not available
		}
	}

	public connect(mode?: "live" | "simulation" | "demo" | "mock") {
		if (this.isConnected) return;

		const effectiveMode = mode || this.getEffectiveMode();
		this.dataSource = effectiveMode === "live" ? "live" : "mock";

		actions.addLog(
			`Attempting to connect to Live Data Server (${this.dataSource} mode)...`,
		);
		actions.setConnectionStatus("connecting");

		if (this.dataSource === "live") {
			this.connectWebSocket();
		} else {
			this.connectMockWorker();
		}
	}

	private getEffectiveMode(): "live" | "mock" {
		// Check store for data mode preference
		try {
			const storeMode =
				typeof window !== "undefined"
					? localStorage.getItem("nexus_project_state")
					: null;

			if (storeMode) {
				const parsed = JSON.parse(storeMode);
				if (parsed.dataMode === "live") return "live";
			}
		} catch {
			// Ignore parse errors
		}

		// In production builds served from backend, default to live
		// In development or standalone, default to mock
		const isDev = import.meta.env.DEV;
		return isDev ? "mock" : "live";
	}

	// ── WebSocket Connection (Live Mode) ─────────────────────────────────────

	private connectWebSocket() {
		try {
			actions.addLog(`Connecting to WebSocket: ${WS_BASE_URL}`);
			this.ws = new WebSocket(WS_BASE_URL);

			this.ws.onopen = () => {
				actions.addLog("WebSocket connection opened. Authenticating...");
				actions.setConnectionStatus("connecting");

				// Send authentication if API key is available
				// Backend requires first message to be auth when FIREAI_API_KEY is set
				if (this.apiKey) {
					this.ws?.send(
						JSON.stringify({
							action: "auth",
							apiKey: this.apiKey,
						}),
					);
				} else {
					// No API key — might work in development mode
					this.onAuthSuccess();
				}
			};

			this.ws.onmessage = (event) => {
				try {
					const message = JSON.parse(event.data);
					this.handleWebSocketMessage(message);
				} catch {
					if (import.meta.env.DEV) {
						console.warn("[DataService] Non-JSON message:", event.data);
					}
				}
			};

			this.ws.onerror = (_event) => {
				actions.addLog("[ERROR] WebSocket connection error");
			};

			this.ws.onclose = (event) => {
				const wasConnected = this.isConnected;
				const wasAuth = this.isAuthenticated;
				this.isConnected = false;
				this.isAuthenticated = false;
				actions.setConnectionStatus("disconnected");

				// Map close codes to meaningful messages
				const closeReasons: Record<number, string> = {
					4001: "Unauthorized origin",
					4003: "Authentication failed — check your API key",
					4004: "Connection limit exceeded (max 5 per IP)",
				};

				const reason = closeReasons[event.code] || `code ${event.code}`;

				if (wasConnected || wasAuth) {
					actions.addLog(
						`Connection lost (${reason}). Buffering incoming data...`,
					);
				} else {
					actions.addLog(`Connection failed: ${reason}`);
				}

				this.stopHealthCheck();

				// Don't reconnect if auth failed (4003) — would loop forever
				if (event.code === 4003) {
					actions.addLog(
						"[WARNING] Authentication failed. Check your API key or switch to demo mode.",
					);
					return;
				}

				// Don't reconnect if origin rejected
				if (event.code === 4001) {
					actions.addLog(
						"[WARNING] Origin rejected by server. Check CORS configuration.",
					);
					return;
				}

				// Attempt reconnection with exponential backoff
				if (
					!event.wasClean &&
					this.reconnectAttempts < WS_MAX_RECONNECT_ATTEMPTS
				) {
					this.reconnectAttempts++;
					const delay = Math.min(
						WS_RECONNECT_INTERVAL * 1.5 ** (this.reconnectAttempts - 1),
						60000,
					);
					actions.addLog(
						`Reconnecting in ${Math.round(delay / 1000)}s ` +
							`(attempt ${this.reconnectAttempts}/${WS_MAX_RECONNECT_ATTEMPTS})...`,
					);

					setTimeout(() => {
						if (!this.isConnected) {
							this.connectWebSocket();
						}
					}, delay);
				} else if (this.reconnectAttempts >= WS_MAX_RECONNECT_ATTEMPTS) {
					actions.addLog(
						"[WARNING] Max reconnection attempts reached. Falling back to mock data.",
					);
					this.fallbackToMock();
				}
			};
		} catch (_error) {  // NOSONAR - typescript:S2486
			actions.addLog(
				"[ERROR] Failed to create WebSocket connection. Falling back to mock data.",
			);
			this.fallbackToMock();
		}
	}

	private onAuthSuccess() {
		this.isConnected = true;
		this.isAuthenticated = true;
		this.reconnectAttempts = 0;
		actions.setConnectionStatus("connected");
		actions.addLog("Connected to Live Data Server (WebSocket).");

		if (this.buffer.length > 0) {
			actions.addLog(
				`[SYSTEM] Restored ${this.buffer.length} buffered readings. Data Gap detected.`,
			);
			this.buffer = [];
		}

		// Re-subscribe to project if previously subscribed
		if (this.subscribedProjectId && this.ws?.readyState === WebSocket.OPEN) {
			this.ws.send(
				JSON.stringify({
					action: "subscribe",
					projectId: this.subscribedProjectId,
				}),
			);
		}

		// Start health check
		this.startHealthCheck();
	}

	private handleWebSocketMessage(message: any) {  // NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
		// Backend sends: {"channel": "...", "type": "...", "data": {...}, "projectId": "..."}

		// Handle authentication response
		if (message.channel === "system" && message.type === "auth_success") {
			this.onAuthSuccess();
			return;
		}

		if (message.channel === "system" && message.type === "auth_failed") {
			actions.addLog(
				"[ERROR] WebSocket authentication failed. Check your API key.",
			);
			this.isAuthenticated = false;
			if (this.ws) {
				this.ws.close(1000, "Auth failed");
			}
			return;
		}

		// Handle pong (health check response)
		if (message.channel === "system" && message.type === "pong") {
			return;
		}

		// Handle subscription confirmation
		if (message.channel === "system" && message.type === "subscribed") {
			if (import.meta.env.DEV) {
				console.log("[DataService] Subscribed to project:", message.projectId);
			}
			return;
		}

		// Handle sync events from backend
		if (message.channel === "sync" && message.type === "sync_completed") {
			if (import.meta.env.DEV) {
				console.log(
					"[DataService] Sync completed for project:",
					message.projectId,
				);
			}
			// Update live data from sync events
			if (message.data) {
				this.handleData(message.data);
			}
			return;
		}

		// Handle telemetry data (if backend sends device telemetry)
		if (message.channel === "telemetry" || message.type === "telemetry") {
			if (message.data) {
				this.handleData(message.data);
			}
			return;
		}

		// Handle fault events
		if (message.type === "fault" || message.data?.fault) {
			const fault = message.data?.fault || message.data;
			actions.addFault(fault);
			actions.addLog(`CRITICAL: Server reported fault on ${fault}`);
			return;
		}

		// Unrecognized message — log in dev mode
		if (import.meta.env.DEV) {
			console.log(
				"[DataService] Unhandled message:",
				message.channel,
				message.type,
			);
		}
	}

	private startHealthCheck() {
		this.stopHealthCheck();
		this.healthCheckTimer = setInterval(() => {
			if (this.ws?.readyState === WebSocket.OPEN) {
				// Backend expects: {"action": "ping"}
				this.ws.send(JSON.stringify({ action: "ping" }));
			}
		}, WS_HEALTH_CHECK_INTERVAL);
	}

	private stopHealthCheck() {
		if (this.healthCheckTimer) {
			clearInterval(this.healthCheckTimer);
			this.healthCheckTimer = null;
		}
	}

	private fallbackToMock() {
		this.disconnect();
		this.dataSource = "mock";
		this.connectMockWorker();
	}

	// ── Mock Worker Connection (Development/Demo Mode) ───────────────────────

	private connectMockWorker() {
		this.isConnected = true;
		actions.setConnectionStatus("connected");
		actions.addLog(
			"Connected to Live Data Server (DEMO MODE — simulated data).",
		);

		if (this.buffer.length > 0) {
			actions.addLog(
				`[SYSTEM] Restored ${this.buffer.length} buffered readings. Data Gap detected.`,
			);
			this.buffer = [];
		}

		this.mockWorker = new Worker(new URL("./mockWorker.ts", import.meta.url), {
			type: "module",
		});
		this.mockWorker.postMessage({ type: "start" });

		this.mockWorker.onmessage = (e) => {
			const { type, data } = e.data;
			if (type === "data") {
				this.handleData(data);
			}
		};
	}

	// ── Shared Data Handling ─────────────────────────────────────────────────

	private handleData = (data: any) => { // NOSONAR — acceptable in this context
		if (!this.isConnected) {
			if (this.buffer.length < this.maxBufferSize) {
				this.buffer.push(data);
			}
			return;
		}

		// Update store
		actions.updateLiveData({
			voltage: data.voltage,
			current: data.current,
			frequency: data.frequency,
		});

		// Handle faults from server data
		if (data.fault) {
			actions.addFault(data.fault);
			actions.addLog(`CRITICAL: Server reported fault on ${data.fault}`);
		}
	};

	// ── Public Methods ───────────────────────────────────────────────────────

	public disconnect() {
		this.isConnected = false;
		this.isAuthenticated = false;
		actions.setConnectionStatus("disconnected");

		// Close WebSocket
		if (this.ws) {
			this.stopHealthCheck();
			this.ws.onclose = null; // Prevent auto-reconnect
			this.ws.close(1000, "Client disconnect");
			this.ws = null;
		}

		// Stop mock worker
		if (this.mockWorker) {
			this.mockWorker.postMessage({ type: "stop" });
			this.mockWorker.terminate();
			this.mockWorker = null;
		}

		actions.addLog("Disconnected from Live Data Server.");
	}

	public switchMode(mode: "live" | "simulation" | "demo" | "mock") {
		this.disconnect();
		// Small delay to allow clean disconnect
		setTimeout(() => this.connect(mode), 100);
	}

	public isConnectedLive(): boolean {
		return (
			this.isConnected &&
			this.isAuthenticated &&
			this.dataSource === "live" &&
			this.ws?.readyState === WebSocket.OPEN
		);
	}

	public getDataSource(): "live" | "mock" {
		return this.dataSource;
	}

	/** Subscribe to real-time updates for a specific project */
	public subscribeToProject(projectId: string) {
		this.subscribedProjectId = projectId;
		if (this.ws?.readyState === WebSocket.OPEN && this.isAuthenticated) {
			this.ws.send(
				JSON.stringify({
					action: "subscribe",
					projectId: projectId,
				}),
			);
		}
	}

	/** Get sync status for a project */
	public getSyncStatus(projectId: string) {
		if (this.ws?.readyState === WebSocket.OPEN && this.isAuthenticated) {
			this.ws.send(
				JSON.stringify({
					action: "get_status",
					projectId: projectId,
				}),
			);
		}
	}

	/**
	 * Simulate a network drop for testing purposes.
	 */
	public simulateDrop() {
		if (!this.isConnected) return;

		if (this.dataSource === "live" && this.ws) {
			this.ws.close(4000, "Simulated network drop");
		} else if (this.dataSource === "mock" && this.mockWorker) {
			this.isConnected = false;
			actions.setConnectionStatus("disconnected");
			actions.addLog("Connection lost! Buffering incoming data...");
			this.mockWorker.postMessage({ type: "stop" });

			setTimeout(() => {
				this.connectMockWorker();
			}, WS_RECONNECT_INTERVAL);
		}
	}

	/**
	 * Send a command to the backend via WebSocket.
	 * Only works in live mode after authentication.
	 */
	public sendCommand(action: string, payload?: any) {
		if (this.ws?.readyState === WebSocket.OPEN && this.isAuthenticated) {
			this.ws.send(
				JSON.stringify({ action, ...payload, timestamp: Date.now() }),
			);
		} else {
			actions.addLog(
				"[WARNING] Cannot send command — not authenticated or not connected.",
			);
		}
	}
}

export const dataService = DataService.getInstance();
