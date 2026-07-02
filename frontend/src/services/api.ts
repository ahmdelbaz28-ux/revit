import type {
  UdmApiResponse,
  UdmPaginatedData,
  Element,
  ElementCreate,
  ElementUpdate,
  ElementsListParams,
  UdmProject,
  ProjectCreate,
  ProjectUpdate,
  UdmConnection,
  ConnectionCreate,
  ConnectionsListParams,
  Conflict,
  ConflictsListParams,
  Statistics,
  HealthStatus,
} from '@/types';
import { getApiKey } from './apiKey';

// V187 FIX: Use VITE_API_URL env var (same pattern as digitalTwinApi.ts).
// Previously this was hardcoded to '/api/v1' (relative), which caused all
// API requests to go to the Vercel frontend domain instead of the backend.
// On Vercel, '/api/v1/conflicts/detect' returned 405 (Method Not Allowed)
// because Vercel serves static files and doesn't accept POST to SPA routes.
// Now uses the same env var as digitalTwinApi.ts, which is set to the HF
// Space backend URL in production.
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

/**
 * M-3 FIX: Session-based auth with HttpOnly cookie.
 *
 * The API key is NO LONGER stored in sessionStorage (which is XSS-readable).
 * Instead, the frontend calls POST /api/v1/auth/login once, which sets an
 * HttpOnly cookie that the browser automatically attaches to all subsequent
 * requests. JavaScript cannot read the cookie, so XSS cannot steal the key.
 *
 * For backwards compatibility:
 *  - VITE_FIREAI_API_KEY env var still works (for SSR / CLI / headless builds)
 *  - sessionStorage 'fireai_settings' still works (legacy, deprecated, will be removed in v2)
 *  - If neither is set, the browser cookie handles auth automatically (no header needed)
 */
// V184: getApiKey() is now imported from ./apiKey (line 19). The local
// duplicate definition was removed to avoid a redeclaration error.

/**
 * M-3: Login with API key to establish an HttpOnly session cookie.
 * After calling this, all subsequent API requests will be authenticated
 * via the cookie — no need to set X-API-Key header manually.
 *
 * @returns The user's role if login succeeds, throws ApiError otherwise.
 */
export async function login(apiKey: string): Promise<{ role: string }> {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new ApiError(body.message || body.detail || 'Login failed', resp.status);
  }
  const body = await resp.json();
  return body.data;
}

/**
 * M-3: Logout — clears the session cookie.
 */
export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
  });
}

/**
 * M-3: Check current session — returns the role if authenticated.
 */
export async function getCurrentUser(): Promise<{ role: string } | null> {
  const resp = await fetch(`${API_BASE}/auth/me`, {
    credentials: 'same-origin',
  });
  if (!resp.ok) return null;
  const body = await resp.json();
  return body.data;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

class ApiClient {
  /**
   * Fetch with retry and exponential backoff.
   * Extracts `data` from the `{success, data, message}` response wrapper.
   * C-1 FIX: Includes X-API-Key header when available for production auth.
   */
  private async fetchWithRetry<T>(
    url: string,
    options?: RequestInit,
    retries = 3
  ): Promise<T> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);

        // Build headers with optional API key
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };
        const apiKey = getApiKey();
        if (apiKey) {
          headers['X-API-Key'] = apiKey;
        }
        // Merge caller headers (can override Content-Type for file uploads)
        if (options?.headers) {
          const callerHeaders = options.headers as Record<string, string>;
          Object.assign(headers, callerHeaders);
        }

        const response = await fetch(`${API_BASE}${url}`, {
          ...options,
          headers,
          signal: controller.signal,
          // M-3: Send cookies (HttpOnly session) with same-origin requests.
          // This is REQUIRED for the cookie-based auth to work.
          credentials: 'same-origin',
        });

        clearTimeout(timeout);

        if (!response.ok) {
          const errorBody = await response.text().catch(() => '');
          throw new ApiError(
            errorBody || `HTTP ${response.status}: ${response.statusText}`,
            response.status
          );
        }

        const json: UdmApiResponse<T> = await response.json();

        if (!json.success) {
          throw new ApiError(json.message || 'API request failed', response.status);
        }

        // Extract data from the wrapper
        return json.data as T;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        // Don't retry on client errors (4xx) except 429
        if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 429) {
          throw error;
        }

        // Exponential backoff: 1s, 2s, 4s
        if (attempt < retries - 1) {
          const delay = Math.pow(2, attempt) * 1000;
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
    }

    throw lastError ?? new Error('Request failed after retries');
  }

  // ===== Elements API =====

  async getElements(params?: ElementsListParams): Promise<UdmPaginatedData<Element>> {
    const searchParams = new URLSearchParams();
    if (params?.element_type) searchParams.set('element_type', params.element_type);
    if (params?.project_id) searchParams.set('project_id', params.project_id);
    if (params?.is_deleted !== undefined) searchParams.set('is_deleted', String(params.is_deleted));
    if (params?.page !== undefined) searchParams.set('page', String(params.page));
    if (params?.page_size !== undefined) searchParams.set('page_size', String(params.page_size));
    if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
    const query = searchParams.toString();
    return this.fetchWithRetry<UdmPaginatedData<Element>>(`/elements${query ? `?${query}` : ''}`);
  }

  async getElement(id: string): Promise<Element> {
    return this.fetchWithRetry<Element>(`/elements/${encodeURIComponent(id)}`);
  }

  async createElement(data: ElementCreate): Promise<Element> {
    return this.fetchWithRetry<Element>('/elements', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateElement(id: string, data: ElementUpdate): Promise<Element> {
    return this.fetchWithRetry<Element>(`/elements/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteElement(id: string): Promise<void> {
    await this.fetchWithRetry<void>(`/elements/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  }

  // ===== Projects API =====
  // The /api/projects endpoint is served by System A (Digital Twin backend).
  // System A returns project objects with camelCase fields:
  //   {id, name, description, author, createdAt, updatedAt, status, deviceCount, connectionCount}
  // The api.ts client uses snake_case Project type from @/types:
  //   {project_id, name, description, status, metadata, element_count, created_timestamp, last_modified_timestamp}
  // We MUST map field names here so components receive correctly shaped data.
  // Failure to map causes undefined field access at runtime (project.project_id = undefined).

  /** Map a System A project object to the System B Project type expected by @/types */
  private _mapProjectFromSystemA(raw: Record<string, unknown>): UdmProject {
    return {
      project_id: (raw.id as string) || '',
      name: (raw.name as string) || '',
      description: (raw.description as string) || undefined,
      status: (raw.status as string) || 'draft',
      metadata: raw.author ? { author: raw.author } : undefined,
      element_count: (raw.deviceCount as number) || 0,
      created_timestamp: (raw.createdAt as string) || null,
      last_modified_timestamp: (raw.updatedAt as string) || null,
    };
  }

  async getProjects(params?: { status?: string; page?: number; page_size?: number }): Promise<UdmPaginatedData<UdmProject>> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page !== undefined) {
      searchParams.set('page', String(params.page));
    }
    // System A uses 'limit' not 'page_size' — convert for compatibility
    if (params?.page_size !== undefined) {
      searchParams.set('limit', String(params.page_size));
    }
    const query = searchParams.toString();
    const raw = await this.fetchWithRetry<{data: Record<string, unknown>[]; total: number; page: number; limit: number; totalPages: number}>(`/projects${query ? `?${query}` : ''}`);
    // Adapt System A format to PaginatedData format AND map field names
    const mappedProjects = (raw.data || []).map(p => this._mapProjectFromSystemA(p));
    return {
      items: mappedProjects,
      total: raw.total,
      page: raw.page,
      page_size: raw.limit,
      total_pages: raw.totalPages,
    };
  }

  async getProject(id: string): Promise<UdmProject> {
    const raw = await this.fetchWithRetry<Record<string, unknown>>(`/projects/${encodeURIComponent(id)}`);
    return this._mapProjectFromSystemA(raw);
  }

  async createProject(data: ProjectCreate): Promise<UdmProject> {
    const raw = await this.fetchWithRetry<Record<string, unknown>>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return this._mapProjectFromSystemA(raw);
  }

  async updateProject(id: string, data: ProjectUpdate): Promise<UdmProject> {
    const raw = await this.fetchWithRetry<Record<string, unknown>>(`/projects/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    return this._mapProjectFromSystemA(raw);
  }

  async deleteProject(id: string): Promise<void> {
    await this.fetchWithRetry<void>(`/projects/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  }

  // ===== Connections API =====

  async getConnections(params?: ConnectionsListParams): Promise<UdmPaginatedData<UdmConnection>> {
    const searchParams = new URLSearchParams();
    if (params?.project_id) searchParams.set('project_id', params.project_id);
    if (params?.element_id) searchParams.set('element_id', params.element_id);
    if (params?.relationship_type) searchParams.set('relationship_type', params.relationship_type);
    if (params?.page !== undefined) searchParams.set('page', String(params.page));
    if (params?.page_size !== undefined) searchParams.set('page_size', String(params.page_size));
    const query = searchParams.toString();
    return this.fetchWithRetry<UdmPaginatedData<UdmConnection>>(`/connections${query ? `?${query}` : ''}`);
  }

  async createConnection(data: ConnectionCreate): Promise<UdmConnection> {
    return this.fetchWithRetry<UdmConnection>('/connections', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateConnection(id: string, data: Partial<ConnectionCreate>): Promise<UdmConnection> {
    return this.fetchWithRetry<UdmConnection>(`/connections/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteConnection(id: string): Promise<void> {
    await this.fetchWithRetry<void>(`/connections/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  }

  // ===== Conflicts API =====

  async getConflicts(params?: ConflictsListParams): Promise<UdmPaginatedData<Conflict>> {
    const searchParams = new URLSearchParams();
    if (params?.resolved !== undefined) searchParams.set('resolved', String(params.resolved));
    if (params?.conflict_type) searchParams.set('conflict_type', params.conflict_type);
    if (params?.page !== undefined) searchParams.set('page', String(params.page));
    if (params?.page_size !== undefined) searchParams.set('page_size', String(params.page_size));
    const query = searchParams.toString();
    return this.fetchWithRetry<UdmPaginatedData<Conflict>>(`/conflicts${query ? `?${query}` : ''}`);
  }

  async detectConflicts(): Promise<Conflict[]> {
    return this.fetchWithRetry<Conflict[]>('/conflicts/detect', {
      method: 'POST',
    });
  }

  async resolveConflict(id: string, strategy: string): Promise<Conflict> {
    return this.fetchWithRetry<Conflict>(`/conflicts/${encodeURIComponent(id)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ strategy }),
    });
  }

  // ===== Reports / Statistics API =====

  async getStatistics(): Promise<Statistics> {
    return this.fetchWithRetry<Statistics>('/reports/statistics');
  }

  // ===== Health API =====

  async healthCheck(): Promise<HealthStatus> {
    return this.fetchWithRetry<HealthStatus>('/health');
  }
}

export const api = new ApiClient();
export { ApiError };
