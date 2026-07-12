
import type {
        Conflict,
        ConflictsListParams,
        ConnectionCreate,
        ConnectionsListParams,
        Element,
        ElementCreate,
        ElementsListParams,
        ElementUpdate,
        HealthStatus,
        ProjectCreate,
        ProjectUpdate,
        Statistics,
        UdmApiResponse,
        UdmConnection,
        UdmPaginatedData,
        UdmProject,
} from "@/types";
import { getApiKey } from "./apiKey";
import {
        CSRF_HEADER_NAME,
        getCsrfToken,
        getCachedCsrfToken,
        invalidateCsrfToken,
} from "./csrf";

// V187 FIX: Use VITE_API_URL env var (same pattern as digitalTwinApi.ts).
// Previously this was hardcoded to '/api/v1' (relative), which caused all
// API requests to go to the Vercel frontend domain instead of the backend.
// On Vercel, '/api/v1/conflicts/detect' returned 405 (Method Not Allowed)
// because Vercel serves static files and doesn't accept POST to SPA routes.
// Now uses the same env var as digitalTwinApi.ts, which is set to the HF
// Space backend URL in production.
const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

// V189 FIX (CRITICAL): camelCase → snake_case transformer.
// ============================================================
// ROOT CAUSE: The backend's CamelModel base class (backend/schemas.py:73)
// uses `alias_generator=_to_camel`, so ALL response fields are serialized
// as camelCase (e.g., `elementId`, `fromElementId`, `connectionId`).
//
// But the frontend types in src/types/index.ts use snake_case (e.g.,
// `element_id`, `from_element_id`, `connection_id`) — and the comment at
// line 6 of that file WRONGLY claims "Field naming: snake_case (matching
// Python/DB conventions)".
//
// Before V188, this mismatch was HIDDEN because the Connections V2 API
// always returned 500 (the tuple-mutation crash). So `connections` was
// always `[]` and the `.slice()` call on `from_element_id` was never
// reached. After V188 fixed the API, real data started flowing — and
// the page crashed with:
//   "TypeError: Cannot read properties of undefined (reading 'slice')"
//
// This same crash would affect Elements.tsx and Conflicts.tsx IF those
// tables had data — but they're currently empty, so the crash is dormant.
//
// Root-cause fix per Rule 17: transform ALL API responses from camelCase
// to snake_case at the API boundary (fetchWithRetry). This way:
//   1. All existing snake_case types continue to work unchanged
//   2. All pages (Elements, Connections, Conflicts, Projects) benefit
//   3. No need to edit every page individually
//   4. The transformer is the SINGLE source of truth for the contract
//
// Why not change the backend to return snake_case? Because:
//   - The CamelModel pattern is used by ALL response schemas (not just
//     UDM) — changing it would break the Projects API, Devices API, etc.
//   - The backend OpenAPI spec documents camelCase as the contract
//   - camelCase is the JSON API convention (JavaScript style)
//
// Why not change the frontend types to camelCase? Because:
//   - There are 30+ field accesses across 6 page components
//   - The types are also used for request bodies (where the backend
//     accepts both snake_case and camelCase via populate_by_name=True)
//   - High risk of introducing new bugs during a mass rename
//
// The transformer is the safest, most targeted fix.
// ============================================================

/**
 * Convert a single camelCase string to snake_case.
 * "fromElementId" → "from_element_id"
 * "connectionId"  → "connection_id"
 * "elementType"   → "element_type"
 */
function camelToSnake(key: string): string {
        // Only transform keys that contain a lowercase→uppercase boundary
        // (i.e., actual camelCase). Keys that are already snake_case, all-caps,
        // or single words pass through unchanged.
        if (!/[a-z]/.test(key) || !/[A-Z]/.test(key)) {
                return key;
        }
        return key.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

/**
 * V191 FIX: Fields that contain FREEFORM user-stored data (dict[str, Any]).
 * These must NOT have their keys transformed, because the user may have
 * stored camelCase keys that are semantically meaningful to their code.
 *
 * V189's transformer transformed ALL keys recursively, including those
 * inside `metadata`. This caused SILENT DATA CORRUPTION: if a user stored
 * `{"cableSize": "2.5mm²"}` in connection metadata, the transformer
 * renamed it to `{"cable_size": "2.5mm²"}`. User code expecting
 * `cableSize` would then see `undefined` — a silent, hard-to-debug break.
 *
 * Root-cause fix per Rule 17: maintain a set of known freeform field names
 * (from backend/schemas.py). When the transformer encounters a key in
 * this set, it transforms the KEY (e.g., changeA → change_a) but does
 * NOT recurse into the VALUE — preserving the user's original keys.
 *
 * These field names are checked in BOTH camelCase and snake_case forms
 * for robustness (the parent key may already have been transformed).
 */
const FREEFORM_DATA_FIELDS = new Set([
        "metadata",
        "resolution",
        "change_a",
        "changeA",
        "change_b",
        "changeB",
]);

/**
 * Deeply transform all object keys from camelCase to snake_case.
 * - Arrays: each element is transformed recursively
 * - Objects: each key is converted, each value is transformed recursively
 *   EXCEPT for freeform data fields (metadata, resolution, change_a/b)
 *   whose VALUES are preserved as-is to prevent user-data corruption.
 * - Primitives (string, number, boolean, null): returned as-is
 *
 * V191 FIX: The V189 transformer recursively transformed ALL nested
 * objects, including freeform `metadata` dicts. This corrupted
 * user-stored camelCase keys. Now, freeform data fields have their
 * KEY transformed (for consistency) but their VALUE is passed through
 * unchanged, preserving the user's original key names.
 */
function deepCamelToSnake<T>(value: T): T {
        if (value === null || value === undefined) {
                return value;
        }
        if (Array.isArray(value)) {
                return value.map(deepCamelToSnake) as unknown as T;
        }
        if (typeof value === "object" && value.constructor === Object) {
                const result: Record<string, unknown> = {};
                for (const key of Object.keys(value as Record<string, unknown>)) {
                        const snakeKey = camelToSnake(key);
                        const val = (value as Record<string, unknown>)[key];
                        // V191 FIX: Don't recurse into freeform data fields — their
                        // keys are user-defined and must be preserved as-is.
                        if (FREEFORM_DATA_FIELDS.has(key) || FREEFORM_DATA_FIELDS.has(snakeKey)) {
                                result[snakeKey] = val;
                        } else {
                                result[snakeKey] = deepCamelToSnake(val);
                        }
                }
                return result as T;
        }
        // Primitive (string, number, boolean, etc.)
        return value;
}

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
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ api_key: apiKey }),
        });
        if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                throw new ApiError(
                        body.message || body.detail || "Login failed",
                        resp.status,
                );
        }
        const body = await resp.json();
        return body.data;
}

/**
 * M-3: Logout — clears the session cookie.
 */
export async function logout(): Promise<void> {
        await fetch(`${API_BASE}/auth/logout`, {
                method: "POST",
                credentials: "same-origin",
        });
}

/**
 * M-3: Check current session — returns the role if authenticated.
 */
export async function getCurrentUser(): Promise<{ role: string } | null> {
        const resp = await fetch(`${API_BASE}/auth/me`, {
                credentials: "same-origin",
        });
        if (!resp.ok) return null;
        const body = await resp.json();
        return body.data;
}

class ApiError extends Error {
        status: number;
        constructor(message: string, status: number) {
                super(message);
                this.name = "ApiError";
                this.status = status;
        }
}

class ApiClient {
        /**
         * Fetch with retry and exponential backoff.
         * Extracts `data` from the `{success, data, message}` response wrapper.
         * C-1 FIX: Includes X-API-Key header when available for production auth.
         *
         * V193 (R5) FIX: Includes X-CSRF-Token header on state-changing requests
         * (POST/PUT/DELETE/PATCH). The token is fetched lazily from
         * /api/v2/auth/csrf-token and cached. On 403 CSRF rejection, the token
         * is invalidated and the request is retried once with a fresh token.
         */
        private async fetchWithRetry<T>(
                url: string,
                options?: RequestInit,
                retries = 3,
        ): Promise<T> {
                let lastError: Error | null = null;

                // V193 (R5): Determine if this is a state-changing request that
                // needs a CSRF token. GET/HEAD/OPTIONS are exempt.
                const method = (options?.method || "GET").toUpperCase();
                const needsCsrf = ["POST", "PUT", "DELETE", "PATCH"].includes(method);

                for (let attempt = 0; attempt < retries; attempt++) {
                        try {
                                const controller = new AbortController();
                                const timeout = setTimeout(() => controller.abort(), 30000);

                                // Build headers with optional API key
                                const headers: Record<string, string> = {
                                        "Content-Type": "application/json",
                                };
                                const apiKey = getApiKey();
                                if (apiKey) {
                                        headers["X-API-Key"] = apiKey;
                                }
                                // V193 (R5): Inject CSRF token on state-changing requests
                                if (needsCsrf) {
                                        let token = getCachedCsrfToken();
                                        if (!token) {
                                                token = await getCsrfToken();
                                        }
                                        if (token) {
                                                headers[CSRF_HEADER_NAME] = token;
                                        }
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
                                        credentials: "same-origin",
                                });

                                clearTimeout(timeout);

                                // V193 (R5): On 403, check if it was a CSRF rejection.
                                // If so, invalidate the cached token and retry once with a
                                // fresh token. This handles token rotation/expiry gracefully.
                                if (
                                        response.status === 403 &&
                                        needsCsrf &&
                                        attempt === 0
                                ) {
                                        const body = await response.text().catch(() => "");
                                        if (
                                                body.toLowerCase().includes("csrf") ||
                                                body.toLowerCase().includes("token")
                                        ) {
                                                invalidateCsrfToken();
                                                await getCsrfToken(true); // force-refresh
                                                continue; // retry with fresh token
                                        }
                                }

                                if (!response.ok) {
                                        const errorBody = await response.text().catch(() => "");
                                        throw new ApiError(
                                                errorBody || `HTTP ${response.status}: ${response.statusText}`,
                                                response.status,
                                        );
                                }

                                const json: UdmApiResponse<T> = await response.json();

                                if (!json.success) {
                                        throw new ApiError(
                                                json.message || "API request failed",
                                                response.status,
                                        );
                                }

                                // V189 FIX: Transform camelCase response keys to snake_case to match
                                // the frontend types. See deepCamelToSnake() docstring for the full
                                // root-cause analysis.
                                const transformedData = deepCamelToSnake(json.data);

                                // Extract data from the wrapper
                                return transformedData as T;
                        } catch (error) {
                                lastError = error instanceof Error ? error : new Error(String(error));

                                // Don't retry on client errors (4xx) except 429
                                if (
                                        error instanceof ApiError &&
                                        error.status >= 400 &&
                                        error.status < 500 &&
                                        error.status !== 429
                                ) {
                                        throw error;
                                }

                                // Exponential backoff: 1s, 2s, 4s
                                if (attempt < retries - 1) {
                                        const delay = 2 ** attempt * 1000;
                                        await new Promise((resolve) => setTimeout(resolve, delay));
                                }
                        }
                }

                throw lastError ?? new Error("Request failed after retries");
        }

        // ===== Elements API =====

        async getElements(
                params?: ElementsListParams,
        ): Promise<UdmPaginatedData<Element>> {
                const searchParams = new URLSearchParams();
                if (params?.element_type)
                        searchParams.set("element_type", params.element_type);
                if (params?.project_id) searchParams.set("project_id", params.project_id);
                if (params?.is_deleted !== undefined)
                        searchParams.set("is_deleted", String(params.is_deleted));
                if (params?.page !== undefined)
                        searchParams.set("page", String(params.page));
                if (params?.page_size !== undefined)
                        searchParams.set("page_size", String(params.page_size));
                if (params?.sort_by) searchParams.set("sort_by", params.sort_by);
                if (params?.sort_order) searchParams.set("sort_order", params.sort_order);
                const query = searchParams.toString();
                return this.fetchWithRetry<UdmPaginatedData<Element>>(
                        `/elements${query ? `?${query}` : ""}`,  // NOSONAR: typescript:S4624
                );
        }

        async getElement(id: string): Promise<Element> {
                return this.fetchWithRetry<Element>(`/elements/${encodeURIComponent(id)}`);
        }

        async createElement(data: ElementCreate): Promise<Element> {
                return this.fetchWithRetry<Element>("/elements", {
                        method: "POST",
                        body: JSON.stringify(data),
                });
        }

        async updateElement(id: string, data: ElementUpdate): Promise<Element> {
                return this.fetchWithRetry<Element>(`/elements/${encodeURIComponent(id)}`, {
                        method: "PUT",
                        body: JSON.stringify(data),
                });
        }

        async deleteElement(id: string): Promise<void> {
                await this.fetchWithRetry<void>(`/elements/${encodeURIComponent(id)}`, {
                        method: "DELETE",
                });
        }

        // ===== Projects API =====
        // The /api/projects endpoint is served by System A (Digital Twin backend).
        // System A returns project objects with these fields (camelCase from backend,
        // now transformed to snake_case by deepCamelToSnake in fetchWithRetry):
        //   {id, name, description, author, created_at, updated_at, status, device_count, connection_count}
        // The api.ts client uses snake_case UdmProject type from @/types:
        //   {project_id, name, description, status, metadata, element_count, created_timestamp, last_modified_timestamp}
        // We MUST map field names here because System A uses `id` (not `project_id`)
        // and `device_count` (not `element_count`) — these are semantic mismatches
        // that a generic camelToSnake transformer cannot fix.
        //
        // V189 FIX: After adding deepCamelToSnake transformer in fetchWithRetry,
        // the raw object now has snake_case keys (created_at, not createdAt).
        // Updated _mapProjectFromSystemA to read snake_case keys.

        /** Map a System A project object to the System B Project type expected by @/types */
        private _mapProjectFromSystemA(raw: Record<string, unknown>): UdmProject {
                return {
                        project_id: (raw.id as string) || (raw.project_id as string) || "",
                        name: (raw.name as string) || "",
                        description: (raw.description as string) || undefined,
                        status: (raw.status as string) || "draft",
                        metadata: raw.author ? { author: raw.author } : undefined,
                        element_count:
                                (raw.device_count as number) ??
                                (raw.deviceCount as number) ??
                                (raw.element_count as number) ??
                                0,
                        created_timestamp:
                                (raw.created_at as string) ??
                                (raw.createdAt as string) ??
                                (raw.created_timestamp as string) ??
                                null,
                        last_modified_timestamp:
                                (raw.updated_at as string) ??
                                (raw.updatedAt as string) ??
                                (raw.last_modified_timestamp as string) ??
                                null,
                };
        }

        async getProjects(params?: {
                status?: string;
                page?: number;
                page_size?: number;
        }): Promise<UdmPaginatedData<UdmProject>> {
                const searchParams = new URLSearchParams();
                if (params?.status) searchParams.set("status", params.status);
                if (params?.page !== undefined) {
                        searchParams.set("page", String(params.page));
                }
                // System A uses 'limit' not 'page_size' — convert for compatibility
                if (params?.page_size !== undefined) {
                        searchParams.set("limit", String(params.page_size));
                }
                const query = searchParams.toString();
                const url = query ? `/projects?${query}` : "/projects";
                const raw = await this.fetchWithRetry<{
                        data: Record<string, unknown>[];
                        total: number;
                        page: number;
                        limit: number;
                        total_pages: number;
                        totalPages: number;
                }>(url);
                // Adapt System A format to PaginatedData format AND map field names.
                // V189 FIX: deepCamelToSnake now transforms `totalPages` → `total_pages`.
                // Accept both forms for robustness (in case the transformer is removed later).
                const mappedProjects = (raw.data || []).map((p) =>
                        this._mapProjectFromSystemA(p),
                );
                return {
                        items: mappedProjects,
                        total: raw.total,
                        page: raw.page,
                        page_size: raw.limit,
                        total_pages: raw.total_pages ?? raw.totalPages ?? 0,
                };
        }

        async getProject(id: string): Promise<UdmProject> {
                const raw = await this.fetchWithRetry<Record<string, unknown>>(
                        `/projects/${encodeURIComponent(id)}`,
                );
                return this._mapProjectFromSystemA(raw);
        }

        async createProject(data: ProjectCreate): Promise<UdmProject> {
                const raw = await this.fetchWithRetry<Record<string, unknown>>(
                        "/projects",
                        {
                                method: "POST",
                                body: JSON.stringify(data),
                        },
                );
                return this._mapProjectFromSystemA(raw);
        }

        async updateProject(id: string, data: ProjectUpdate): Promise<UdmProject> {
                const raw = await this.fetchWithRetry<Record<string, unknown>>(
                        `/projects/${encodeURIComponent(id)}`,
                        {
                                method: "PUT",
                                body: JSON.stringify(data),
                        },
                );
                return this._mapProjectFromSystemA(raw);
        }

        async deleteProject(id: string): Promise<void> {
                await this.fetchWithRetry<void>(`/projects/${encodeURIComponent(id)}`, {
                        method: "DELETE",
                });
        }

        // ===== Connections API =====

        async getConnections(
                params?: ConnectionsListParams,
        ): Promise<UdmPaginatedData<UdmConnection>> {
                const searchParams = new URLSearchParams();
                if (params?.project_id) searchParams.set("project_id", params.project_id);
                if (params?.element_id) searchParams.set("element_id", params.element_id);
                if (params?.relationship_type)
                        searchParams.set("relationship_type", params.relationship_type);
                if (params?.page !== undefined)
                        searchParams.set("page", String(params.page));
                if (params?.page_size !== undefined)
                        searchParams.set("page_size", String(params.page_size));
                const query = searchParams.toString();
                return this.fetchWithRetry<UdmPaginatedData<UdmConnection>>(
                        `/connections${query ? `?${query}` : ""}`,  // NOSONAR: typescript:S4624
                );
        }

        async createConnection(data: ConnectionCreate): Promise<UdmConnection> {
                return this.fetchWithRetry<UdmConnection>("/connections", {
                        method: "POST",
                        body: JSON.stringify(data),
                });
        }

        async updateConnection(
                id: string,
                data: Partial<ConnectionCreate>,
        ): Promise<UdmConnection> {
                return this.fetchWithRetry<UdmConnection>(
                        `/connections/${encodeURIComponent(id)}`,
                        {
                                method: "PUT",
                                body: JSON.stringify(data),
                        },
                );
        }

        async deleteConnection(id: string): Promise<void> {
                await this.fetchWithRetry<void>(`/connections/${encodeURIComponent(id)}`, {
                        method: "DELETE",
                });
        }

        // ===== Conflicts API =====

        async getConflicts(
                params?: ConflictsListParams,
        ): Promise<UdmPaginatedData<Conflict>> {
                const searchParams = new URLSearchParams();
                if (params?.resolved !== undefined)
                        searchParams.set("resolved", String(params.resolved));
                if (params?.conflict_type)
                        searchParams.set("conflict_type", params.conflict_type);
                if (params?.page !== undefined)
                        searchParams.set("page", String(params.page));
                if (params?.page_size !== undefined)
                        searchParams.set("page_size", String(params.page_size));
                const query = searchParams.toString();
                return this.fetchWithRetry<UdmPaginatedData<Conflict>>(
                        `/conflicts${query ? `?${query}` : ""}`,  // NOSONAR: typescript:S4624
                );
        }

        async detectConflicts(): Promise<Conflict[]> {
                return this.fetchWithRetry<Conflict[]>("/conflicts/detect", {
                        method: "POST",
                });
        }

        async resolveConflict(id: string, strategy: string): Promise<Conflict> {
                return this.fetchWithRetry<Conflict>(
                        `/conflicts/${encodeURIComponent(id)}/resolve`,
                        {
                                method: "POST",
                                body: JSON.stringify({ strategy }),
                        },
                );
        }

        // ===== Reports / Statistics API =====

        async getStatistics(): Promise<Statistics> {
                return this.fetchWithRetry<Statistics>("/reports/statistics");
        }

        // ===== Health API =====

        async healthCheck(): Promise<HealthStatus> {
                return this.fetchWithRetry<HealthStatus>("/health");
        }
}

export const api = new ApiClient();
export { ApiError };
