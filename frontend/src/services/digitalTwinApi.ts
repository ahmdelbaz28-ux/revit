/**
 * digitalTwinApi.ts - REST API Client for Digital Twin Backend (System A)
 *
 * These types correspond to System A — the Digital Twin API.
 * Backend: digital_twin.db, routers: projects.py, devices.py, connections.py, reports.py, health.py
 * Field naming: camelCase (JavaScript/TypeScript conventions)
 *
 * Do NOT confuse with the UDM types in types/index.ts
 * which use snake_case fields and connect to udm_elements.db.
 *
 * Supports retry logic, timeouts, and WebSocket real-time subscription
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';
const API_TIMEOUT = 15000;
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  timestamp: string;
}

export interface PaginationParams {
  page?: number;
  limit?: number;
  sort?: string;
  order?: 'asc' | 'desc';
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

// ============================================================================
// API CLIENT
// ============================================================================

class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;
  private wsConnection: WebSocket | null = null;
  private wsCallbacks: Map<string, Set<(data: unknown) => void>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || API_BASE_URL;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      'X-Client-Version': import.meta.env.VITE_APP_VERSION || '1.0.0',
    };
  }

  setAuthToken(token: string): void {
    this.defaultHeaders['Authorization'] = 'Bearer ' + token;
  }

  clearAuthToken(): void {
    delete this.defaultHeaders['Authorization'];
  }

  private async fetchWithRetry<T>(
    url: string,
    options: RequestInit,
    retries: number = MAX_RETRIES,
  ): Promise<ApiResponse<T>> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

    // If the caller provides an AbortSignal, link it to our controller
    // so that external cancellation also aborts the request.
    const externalSignal = options.signal;
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort();
      } else {
        externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
      }
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers: { ...this.defaultHeaders, ...options.headers },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(data?.error || data?.detail || 'HTTP ' + response.status);
      }

      // ── UNWRAPPING CONTRACT ─────────────────────────────────────────
      // Backend always returns: { success: true, data: <payload> }
      // For paginated responses, <payload> = { data: T[], total, page, ... }
      // For single items, <payload> = { id, name, ... }
      //
      // We extract <payload> from the outer wrapper here, so the hooks
      // in useApi.ts receive it as `res.data`:
      //   - Paginated: res.data = { data: T[], total, page, ... } → res.data.data = T[]
      //   - Single:    res.data = { id, name, ... }
      //
      // IMPORTANT: Hooks access res.data (the payload), not the raw JSON.
      // For paginated endpoints, hooks further access res.data.data for the array.
      // ────────────────────────────────────────────────────────────────
      const payload = data?.data !== undefined ? data.data : data;

      return {
        success: data?.success ?? true,
        data: payload as T,
        message: data?.message,
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      clearTimeout(timeoutId);

      if (retries > 0 && this.isRetryableError(error)) {
        await this.delay(RETRY_DELAY * (MAX_RETRIES - retries + 1));
        return this.fetchWithRetry<T>(url, options, retries - 1);
      }

      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date().toISOString(),
      };
    }
  }

  private isRetryableError(error: unknown): boolean {
    // Don't retry timeout errors (AbortError) — saves user from 45s wait
    if (error instanceof DOMException && error.name === 'AbortError') return false;
    // Retry network failures (TypeError from fetch)
    if (error instanceof TypeError) return true;
    return false;
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // ============================================================================
  // HTTP METHODS
  // ============================================================================

  async get<T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    // Build URL manually — new URL() crashes with relative base like "/api"
    let url = path.startsWith('http') ? path : this.baseUrl + path;
    if (params) {
      const sep = url.includes('?') ? '&' : '?';
      const qs = Object.entries(params)
        .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
        .join('&');
      url += sep + qs;
    }
    return this.fetchWithRetry<T>(url, { method: 'GET' });
  }

  async post<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.fetchWithRetry<T>(path.startsWith('http') ? path : this.baseUrl + path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.fetchWithRetry<T>(path.startsWith('http') ? path : this.baseUrl + path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.fetchWithRetry<T>(path.startsWith('http') ? path : this.baseUrl + path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(path: string): Promise<ApiResponse<T>> {
    return this.fetchWithRetry<T>(path.startsWith('http') ? path : this.baseUrl + path, {
      method: 'DELETE',
    });
  }

  // ============================================================================
  // WEBSOCKET
  // ============================================================================

  connectWebSocket(channel: string, callback: (data: unknown) => void): void {
    // Register the callback for this channel BEFORE connecting
    if (!this.wsCallbacks.has(channel)) {
      this.wsCallbacks.set(channel, new Set());
    }
    this.wsCallbacks.get(channel)!.add(callback);

    if (!this.wsConnection || this.wsConnection.readyState === WebSocket.CLOSED) {
      // CRITICAL FIX: When baseUrl is a relative path like "/api",
      // .replace('http','ws') does nothing (no 'http' in "/api"),
      // and .replace('/api','/ws') produces "/ws" — an INVALID WebSocket URL.
      // WebSocket requires an absolute URL: ws://host/path
      const resolveWsUrl = (): string => {
        const base = this.baseUrl;
        // If VITE_WS_URL env var is explicitly set, use it directly
        const envWsUrl = import.meta.env.VITE_WS_URL;
        if (envWsUrl) {
          return envWsUrl;
        }
        // Relative base URL (default dev case: "/api")
        if (!base.startsWith('http')) {
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const host = window.location.host;
          return `${protocol}//${host}/ws`;
        }
        // Absolute base URL: replace http(s) with ws(s) and strip /api suffix
        return base
          .replace(/^https:/, 'wss:')
          .replace(/^http:/, 'ws:')
          .replace(/\/api\/?$/, '/ws');
      };
      const wsUrl = resolveWsUrl();
      this.wsConnection = new WebSocket(wsUrl);

      this.wsConnection.onopen = () => {
        this.reconnectAttempts = 0;
        if (import.meta.env.DEV) console.log('WebSocket connected');
        // Start heartbeat to detect half-open connections
        this.startHeartbeat();
      };

      this.wsConnection.onclose = () => {
        if (import.meta.env.DEV) console.log('WebSocket disconnected');
        this.scheduleReconnect();
      };

      this.wsConnection.onerror = (error) => {
        if (import.meta.env.DEV) console.error('WebSocket error:', error);
      };

      // Single onmessage handler that dispatches to ALL registered channels.
      // Previous bug: each connectWebSocket() call overwrote onmessage, so only
      // the last channel ever received messages.
      this.wsConnection.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          // Dispatch to the specific channel's callbacks
          const targetChannel = message.channel;
          if (targetChannel && this.wsCallbacks.has(targetChannel)) {
            this.wsCallbacks.get(targetChannel)!.forEach((cb) => cb(message.data));
          }
          // Also dispatch to wildcard listeners (channel "*")
          if (this.wsCallbacks.has('*')) {
            this.wsCallbacks.get('*')!.forEach((cb) => cb(message));
          }
        } catch {
          // Ignore parse errors
        }
      };
    }
  }

  disconnectWebSocket(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    // Stop heartbeat if running
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    this.reconnectAttempts = 0;
    if (this.wsConnection) {
      this.wsConnection.onclose = null; // Prevent reconnection on intentional close
      this.wsConnection.close();
      this.wsConnection = null;
      this.wsCallbacks.clear();
    }
  }

  // ============================================================================
  // CONNECTION STATE & HEARTBEAT
  // ============================================================================

  /** Callback invoked when WebSocket permanently loses connection after max retries.
   *  The UI should display a prominent warning that real-time updates have stopped.
   */
  onConnectionLost?: () => void;

  /** Get current WebSocket connection state for UI indicators. */
  getConnectionState(): 'connecting' | 'connected' | 'disconnected' | 'permanently_lost' {
    if (!this.wsConnection) return 'disconnected';
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return 'permanently_lost';
    switch (this.wsConnection.readyState) {
      case WebSocket.CONNECTING: return 'connecting';
      case WebSocket.OPEN: return 'connected';
      case WebSocket.CLOSING: return 'disconnected';
      case WebSocket.CLOSED: return 'disconnected';
      default: return 'disconnected';
    }
  }

  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  /**
   * Start client-side heartbeat to detect half-open connections.
   *
   * SAFETY FIX: Proxies and firewalls silently drop idle WebSocket connections.
   * Without a heartbeat, the client believes it's connected but no messages flow.
   * Device status updates (faults, alarms) would stop arriving without any error.
   *
   * Sends ping every 30 seconds. If no pong within 10 seconds, force reconnect.
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    let pongReceived = true;

    this.heartbeatTimer = setInterval(() => {
      if (!this.wsConnection || this.wsConnection.readyState !== WebSocket.OPEN) {
        this.stopHeartbeat();
        return;
      }
      if (!pongReceived) {
        // No pong received since last ping — connection is half-open
        if (import.meta.env.DEV) console.warn('WebSocket: heartbeat timeout — forcing reconnect');
        this.wsConnection.close();
        // scheduleReconnect will be triggered by onclose
        this.stopHeartbeat();
        return;
      }
      pongReceived = false;
      try {
        this.wsConnection.send(JSON.stringify({ action: 'ping' }));
      } catch {
        this.stopHeartbeat();
      }
    }, 30000);

    // Listen for pong responses (overlaid on existing onmessage)
    const originalOnMessage = this.wsConnection?.onmessage ?? null;
    this.wsConnection!.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'pong' || data.action === 'pong') {
          pongReceived = true;
          return; // Don't dispatch pong to channel callbacks
        }
      } catch { /* ignore */ }
      // Forward to original handler
      if (originalOnMessage) {
        originalOnMessage.call(this.wsConnection!, event);
      }
    };
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      if (import.meta.env.DEV) console.log('WebSocket: max reconnect attempts reached');
      // SAFETY FIX: Notify application that real-time updates have stopped.
      // Without this, the operator sees stale device data without any indication
      // that the connection is dead — device faults/alarms would not be displayed.
      // Call the connection-lost callback if registered.
      if (this.onConnectionLost) {
        this.onConnectionLost();
      }
      return;
    }
    const delay = 5000 * (this.reconnectAttempts + 1);
    this.reconnectAttempts++;
    if (import.meta.env.DEV) console.log(`WebSocket: reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    this.reconnectTimer = setTimeout(() => {
      if (this.wsConnection && this.wsConnection.readyState === WebSocket.CLOSED) {
        // RACE CONDITION FIX: Nullify wsConnection and clean up heartbeat
        // before reconnecting to prevent duplicate connections.
        this.wsConnection = null;
        this.stopHeartbeat();
        const savedCallbacks = new Map(this.wsCallbacks);
        this.wsCallbacks.clear();
        savedCallbacks.forEach((callbacks, channel) => {
          callbacks.forEach((cb) => this.connectWebSocket(channel, cb));
        });
      }
    }, delay);
  }

  // ============================================================================
  // PROJECT ENDPOINTS
  // ============================================================================

  async getProjects(params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Project>>> {
    return this.get<PaginatedResponse<Project>>('/projects', params as Record<string, string>);
  }

  async getProject(id: string): Promise<ApiResponse<Project>> {
    return this.get<Project>('/projects/' + encodeURIComponent(id));
  }

  async createProject(data: CreateProjectInput): Promise<ApiResponse<Project>> {
    return this.post<Project>('/projects', data);
  }

  async updateProject(id: string, data: UpdateProjectInput): Promise<ApiResponse<Project>> {
    return this.put<Project>('/projects/' + encodeURIComponent(id), data);
  }

  async deleteProject(id: string): Promise<ApiResponse<void>> {
    return this.delete<void>('/projects/' + encodeURIComponent(id));
  }

  // ============================================================================
  // DEVICE ENDPOINTS
  // ============================================================================

  async getDevices(projectId: string, params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Device>>> {
    return this.get<PaginatedResponse<Device>>('/projects/' + encodeURIComponent(projectId) + '/devices', params as Record<string, string>);
  }

  async getDevice(projectId: string, deviceId: string): Promise<ApiResponse<Device>> {
    return this.get<Device>('/projects/' + encodeURIComponent(projectId) + '/devices/' + encodeURIComponent(deviceId));
  }

  async createDevice(projectId: string, data: CreateDeviceInput): Promise<ApiResponse<Device>> {
    return this.post<Device>('/projects/' + encodeURIComponent(projectId) + '/devices', data);
  }

  async updateDevice(projectId: string, deviceId: string, data: UpdateDeviceInput): Promise<ApiResponse<Device>> {
    return this.put<Device>('/projects/' + encodeURIComponent(projectId) + '/devices/' + encodeURIComponent(deviceId), data);
  }

  async deleteDevice(projectId: string, deviceId: string): Promise<ApiResponse<void>> {
    return this.delete<void>('/projects/' + encodeURIComponent(projectId) + '/devices/' + encodeURIComponent(deviceId));
  }

  // ============================================================================
  // CONNECTION ENDPOINTS
  // ============================================================================

  async getConnections(projectId: string, params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Connection>>> {
    return this.get<PaginatedResponse<Connection>>('/projects/' + encodeURIComponent(projectId) + '/connections', params as Record<string, string>);
  }

  async createConnection(projectId: string, data: CreateConnectionInput): Promise<ApiResponse<Connection>> {
    return this.post<Connection>('/projects/' + encodeURIComponent(projectId) + '/connections', data);
  }

  async deleteConnection(projectId: string, connectionId: string): Promise<ApiResponse<void>> {
    return this.delete<void>('/projects/' + encodeURIComponent(projectId) + '/connections/' + encodeURIComponent(connectionId));
  }

  // ============================================================================
  // REPORT ENDPOINTS
  // ============================================================================

  async generateReport(projectId: string, data: GenerateReportInput): Promise<ApiResponse<Report>> {
    return this.post<Report>('/projects/' + encodeURIComponent(projectId) + '/reports', data);
  }

  async getReports(projectId: string, params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Report>>> {
    return this.get<PaginatedResponse<Report>>('/projects/' + encodeURIComponent(projectId) + '/reports', params as Record<string, string>);
  }

  async getReport(projectId: string, reportId: string): Promise<ApiResponse<Report>> {
    return this.get<Report>('/projects/' + encodeURIComponent(projectId) + '/reports/' + encodeURIComponent(reportId));
  }

  async exportReport(projectId: string, reportId: string, format: string): Promise<Blob> {
    return this.fetchBlob(this.baseUrl + '/projects/' + encodeURIComponent(projectId) + '/reports/' + encodeURIComponent(reportId) + '/export?format=' + encodeURIComponent(format));
  }

  // ============================================================================
  // EXPORT ENDPOINTS
  // ============================================================================

  private async fetchBlob(url: string, retries: number = MAX_RETRIES): Promise<Blob> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);
    try {
      // Include API key header (same pattern as api.ts)
      const headers: Record<string, string> = { ...this.defaultHeaders };
      const apiKey = this.getApiKey();
      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }
      const response = await fetch(url, {
        headers,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!response.ok) throw new Error('Export failed: HTTP ' + response.status);
      return response.blob();
    } catch (error) {
      clearTimeout(timeoutId);
      if (retries > 0 && this.isRetryableError(error)) {
        await this.delay(RETRY_DELAY * (MAX_RETRIES - retries + 1));
        return this.fetchBlob(url, retries - 1);
      }
      throw error;
    }
  }

  async exportToDXF(projectId: string): Promise<Blob> {
    return this.fetchBlob(this.baseUrl + '/projects/' + encodeURIComponent(projectId) + '/export/dxf');
  }

  async exportToRevit(projectId: string): Promise<Blob> {
    return this.fetchBlob(this.baseUrl + '/projects/' + encodeURIComponent(projectId) + '/export/revit');
  }

  async exportToIFC(projectId: string, version: string = 'IFC4'): Promise<Blob> {
    return this.fetchBlob(this.baseUrl + '/projects/' + encodeURIComponent(projectId) + '/export/ifc?version=' + encodeURIComponent(version));
  }

  // ============================================================================
  // SYNC ENDPOINTS
  // ============================================================================

  async syncProject(projectId: string): Promise<ApiResponse<SyncStatus>> {
    return this.post<SyncStatus>('/projects/' + encodeURIComponent(projectId) + '/sync');
  }

  async getSyncStatus(projectId: string): Promise<ApiResponse<SyncStatus>> {
    return this.get<SyncStatus>('/projects/' + encodeURIComponent(projectId) + '/sync');
  }

  // ============================================================================
  // HEALTH CHECK
  // ============================================================================

  async healthCheck(): Promise<ApiResponse<HealthStatus>> {
    return this.get<HealthStatus>('/health');
  }

  /**
   * Get API key from environment or runtime config.
   * Mirrors the pattern in api.ts for consistent auth across both API clients.
   */
  private getApiKey(): string | null {
    const envKey = import.meta.env.VITE_FIREAI_API_KEY;
    if (envKey) return envKey;
    try {
      const stored = sessionStorage.getItem('fireai_settings');
      if (stored) {
        const settings = JSON.parse(stored);
        if (settings?.apiKey && typeof settings.apiKey === 'string' && settings.apiKey.trim()) {
          return settings.apiKey.trim();
        }
      }
    } catch {
      // Invalid JSON in sessionStorage — ignore
    }
    return null;
  }
}

// ============================================================================
// TYPES
// ============================================================================

export interface Project {
  id: string;
  name: string;
  description: string;
  author: string;
  createdAt: string;
  updatedAt: string;
  status: 'active' | 'archived' | 'draft';
  deviceCount: number;
  connectionCount: number;
}

export interface CreateProjectInput {
  name: string;
  description?: string;
  author?: string;
}

export interface UpdateProjectInput {
  name?: string;
  description?: string;
  status?: 'active' | 'archived' | 'draft';
}

export interface Device {
  id: string;
  projectId: string;
  type: string;
  name: string;
  category: string;
  x: number;
  y: number;
  z: number;
  rotation: number;
  voltage: number;
  current: number;
  load: number;
  properties: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface CreateDeviceInput {
  type: string;
  name: string;
  category: string;
  x: number;
  y: number;
  z?: number;
  rotation?: number;
  voltage?: number;
  current?: number;
  load?: number;
  load_unit?: 'A' | 'mA' | 'W';
  properties?: Record<string, unknown>;
}

export interface UpdateDeviceInput {
  name?: string;
  x?: number;
  y?: number;
  z?: number;
  rotation?: number;
  voltage?: number;
  current?: number;
  load?: number;
  load_unit?: 'A' | 'mA' | 'W';  // BUG-30 FIX: Required for unit conversion
  properties?: Record<string, unknown>;
}

export interface Connection {
  id: string;
  projectId: string;
  fromId: string;
  toId: string;
  cableSize: string;
  length: number;
  type: string;
  createdAt: string;
}

export interface CreateConnectionInput {
  fromId: string;
  toId: string;
  cableSize?: string;
  length?: number;
  type?: string;
}

export interface Report {
  id: string;
  projectId: string;
  type: string;
  name: string;
  parameters: Record<string, unknown>;
  status: 'pending' | 'completed' | 'failed';
  createdAt: string;
  completedAt?: string;
}

export interface GenerateReportInput {
  type: string;
  name?: string;
  parameters?: Record<string, unknown>;
}

export interface SyncStatus {
  projectId: string;
  status: 'syncing' | 'synced' | 'error';
  lastSync: string;
  pendingChanges: number;
  error?: string;
}

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'error';
  version: string;
  uptime: number;
  database: 'connected' | 'disconnected';
  timestamp: string;
  // Extended fields returned by backend (used by some components)
  uptime_seconds?: number;
  core_modules?: string;
  total_elements?: number;
  total_projects?: number;
  warning?: string;
}

// ============================================================================
// EXPORTED INSTANCE
// ============================================================================

export const api = new ApiClient();
export default api;

// Add CSRF token handling to API requests
let csrfToken: string | null = null;

// Free-function API key getter (mirrors DigitalTwinApi.getApiKey class method).
// Used by the standalone apiRequest() helper below.
function getApiKey(): string | null {
  const envKey = import.meta.env.VITE_FIREAI_API_KEY;
  if (envKey) return envKey;
  try {
    const stored = sessionStorage.getItem('fireai_settings');
    if (stored) {
      const settings = JSON.parse(stored);
      return settings.apiKey ?? null;
    }
  } catch {
    // sessionStorage not available or invalid JSON
  }
  return null;
}

// Function to get CSRF token from meta tag or other source
function getCsrfToken(): string | null {
  if (csrfToken) return csrfToken;
  
  // Try to get from meta tag
  const tokenMeta = document.querySelector('meta[name="csrf-token"]');
  if (tokenMeta) {
    csrfToken = tokenMeta.getAttribute('content');
    return csrfToken;
  }
  
  // If not found, return null
  return null;
}

// Update the API request functions to include CSRF token
async function apiRequest<T>(
  url: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-API-Key': getApiKey() ?? '',
    ...((options.headers as Record<string, string>) ?? {}),
  };

  // Add CSRF token for state-changing requests
  const method = options.method || 'GET';
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const token = getCsrfToken();
    if (token) {
      headers['X-CSRF-Token'] = token;
    }
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const data = await response.json();
    return {
      success: response.ok,
      data: response.ok ? data.data || data : undefined,
      error: response.ok ? undefined : data.error || 'Unknown error',
      timestamp: new Date().toISOString(),
    } as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      data: undefined,
      error: error instanceof Error ? error.message : 'Network error',
      timestamp: new Date().toISOString(),
    } as ApiResponse<T>;
  }
}
