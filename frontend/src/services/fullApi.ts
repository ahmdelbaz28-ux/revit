/**
 * fullApi.ts — Comprehensive API client covering ALL backend endpoints.
 *
 * V140 Phase 5: This module provides typed methods for every backend API
 * endpoint (188 total across 23 routers). Pages import from here instead
 * of maintaining scattered inline fetch() calls.
 *
 * Categories:
 *   - Core CRUD: projects, devices, connections, elements, conflicts, reports
 *   - Engineering: qomn (smoke/heat spacing, battery, voltage drop, detectors)
 *   - FACP: panel selection, verification, scheduling
 *   - Environment: weather, geocode, air quality, hazmat, severe weather
 *   - Revit: 32 endpoints (connect, elements CRUD, families, search)
 *   - AutoCAD: 13 endpoints (connect, draw, entity CRUD)
 *   - Digital Twin: convert, history, mappings, config
 *   - Monitor: health, metrics, engine status, alerts
 *   - Workflow: start, approve, reject, audit
 *   - Memory: store, search, history
 *   - V2: generative design, BIM, IFC43, AR, webhooks, topology, graphrag
 *   - Marine: 14 endpoints (ship design, zones, extinguishing, alarm logic)
 *   - API Keys: CRUD, roles
 *   - Exports: DXF, Revit, IFC
 *   - Health & Cache
 */

import { api as coreApi } from './api';
import { api as digitalTwinApiClient } from './digitalTwinApi';
import { getApiKey } from './apiKey';
import { ApiError } from './api';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  timestamp?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

// ─── API Base Configuration ─────────────────────────────────────────────────

// V187 FIX: Use VITE_API_URL env var (same pattern as digitalTwinApi.ts).
// Previously hardcoded to '/api/v1' which broke POST requests on Vercel.
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';
const API_V2_BASE = (import.meta.env.VITE_API_URL || '/api').replace('/v1', '') + '/v2';

// V184: getApiKey() is now imported from ./apiKey (line 28). The local
// duplicate definition was removed to avoid a redeclaration error.

async function apiCall<T>(
  path: string,
  options: RequestInit = {},
  baseUrl: string = API_BASE
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };
  const apiKey = getApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    signal: options.signal || AbortSignal.timeout(30000),
    // M-3: Send cookies (HttpOnly session) with same-origin requests
    credentials: 'same-origin',
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    // V185 FIX: Throw ApiError (not generic Error) for consistency with api.ts.
    // Consumers were forced to handle two different error types — now they handle one.
    throw new ApiError(
      errorBody?.detail || errorBody?.message || `HTTP ${response.status}: ${response.statusText}`,
      response.status
    );
  }

  // Handle blob responses (file downloads)
  if (response.headers.get('content-type')?.includes('application/octet-stream') ||
      response.headers.get('content-type')?.includes('application/pdf')) {
    return response.blob() as unknown as T;
  }

  const body = await response.json();
  // Unwrap {success, data, message} envelope
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    if (!body.success) {
      // V185 FIX: ApiError for consistency
      throw new ApiError(body.message || 'API returned success=false', response.status);
    }
    return body.data as T;
  }
  return body as T;
}

// ─── Engineering API (QOMN) ─────────────────────────────────────────────────

export const qomnApi = {
  /** POST /qomn/smoke-spacing — Calculate NFPA 72 smoke detector spacing */
  smokeSpacing: (data: {
    room_area: number;
    ceiling_height: number;
    detector_type?: string;
  }) => apiCall('/qomn/smoke-spacing', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /qomn/heat-spacing — Calculate heat detector spacing */
  heatSpacing: (data: {
    room_area: number;
    ceiling_height: number;
    detector_type?: string;
  }) => apiCall('/qomn/heat-spacing', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /qomn/battery — Calculate battery requirements */
  battery: (data: {
    devices: Array<{ type: string; quantity: number; current: number }>;
    duration_hours?: number;
    safety_factor?: number;
  }) => apiCall('/qomn/battery', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /qomn/voltage-drop — Calculate voltage drop */
  voltageDrop: (data: {
    current: number;
    length: number;
    cable_size: string;
    voltage: number;
    material?: string;
  }) => apiCall('/qomn/voltage-drop', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /qomn/place-detectors — Place detectors in a room */
  placeDetectors: (data: {
    room_polygon: Array<[number, number]>;
    detector_type: string;
    spacing?: number;
  }) => apiCall('/qomn/place-detectors', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /qomn/place-duct — Place duct detector */
  placeDuct: (data: {
    duct_width: number;
    duct_height: number;
    airflow_cfm: number;
  }) => apiCall('/qomn/place-duct', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** GET /qomn/audit — Get QOMN audit trail */
  getAudit: () => apiCall('/qomn/audit'),

  /** GET /qomn/physics-guards — Get physics guard status */
  getPhysicsGuards: () => apiCall('/qomn/physics-guards'),

  /** GET /qomn/constants — Get QOMN constants */
  getConstants: () => apiCall('/qomn/constants'),

  /** POST /qomn/golden-tests — Run golden tests */
  runGoldenTests: (data: { test_ids?: string[] }) => apiCall('/qomn/golden-tests', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// ─── FACP API ───────────────────────────────────────────────────────────────

export const facpApi = {
  /** POST /facp/select — Select FACP panel */
  select: (data: {
    building_type: string;
    total_devices: number;
    total_zones: number;
    notification_appliances: number;
  }) => apiCall('/facp/select', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /facp/verify — Verify FACP selection */
  verify: (data: { panel_id: string; requirements: Record<string, unknown> }) =>
    apiCall('/facp/verify', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /facp/schedule — Generate FACP schedule */
  schedule: (data: { panel_id: string; zones: Array<Record<string, unknown>> }) =>
    apiCall('/facp/schedule', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /facp/spec — Generate FACP specification */
  spec: (data: { panel_id: string; project_info: Record<string, unknown> }) =>
    apiCall('/facp/spec', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /facp/panels — List all FACP panels */
  getPanels: () => apiCall('/facp/panels'),
};

// ─── Environment API ────────────────────────────────────────────────────────

export const environmentApi = {
  /** GET /environment/countries */
  getCountries: () => apiCall('/environment/countries'),

  /** GET /environment/weather?lat=&lon= */
  getWeather: (lat: number, lon: number) =>
    apiCall(`/environment/weather?lat=${lat}&lon=${lon}`),

  /** GET /environment/geocode?address= */
  geocode: (address: string) =>
    apiCall(`/environment/geocode?address=${encodeURIComponent(address)}`),

  /** GET /environment/region?lat=&lon= */
  getRegion: (lat: number, lon: number) =>
    apiCall(`/environment/region?lat=${lat}&lon=${lon}`),

  /** GET /environment/elevation?lat=&lon= */
  getElevation: (lat: number, lon: number) =>
    apiCall(`/environment/elevation?lat=${lat}&lon=${lon}`),

  /** GET /environment/air-quality?lat=&lon= */
  getAirQuality: (lat: number, lon: number) =>
    apiCall(`/environment/air-quality?lat=${lat}&lon=${lon}`),

  /** GET /environment/severe-weather?lat=&lon= */
  getSevereWeather: (lat: number, lon: number) =>
    apiCall(`/environment/severe-weather?lat=${lat}&lon=${lon}`),

  /** GET /environment/hazmat?substance= */
  getHazmat: (substance: string) =>
    apiCall(`/environment/hazmat?substance=${encodeURIComponent(substance)}`),

  /** GET /environment/hazmat/known */
  getKnownHazmat: () => apiCall('/environment/hazmat/known'),

  /** GET /environment/context?lat=&lon= */
  getContext: (lat: number, lon: number) =>
    apiCall(`/environment/context?lat=${lat}&lon=${lon}`),

  /** GET /environment/full-context?lat=&lon= */
  getFullContext: (lat: number, lon: number) =>
    apiCall(`/environment/full-context?lat=${lat}&lon=${lon}`),
};

// ─── Revit API ──────────────────────────────────────────────────────────────

export const revitApi = {
  /** POST /revit/connect */
  connect: (data: { visible?: boolean; force_new?: boolean } = {}) =>
    apiCall('/revit/connect', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/disconnect */
  disconnect: () => apiCall('/revit/disconnect', { method: 'POST' }),

  /** GET /revit/status */
  getStatus: () => apiCall('/revit/status'),

  /** POST /revit/document/open */
  openDocument: (data: { filepath: string }) =>
    apiCall('/revit/document/open', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/document/save */
  saveDocument: (data: { filepath?: string }) =>
    apiCall('/revit/document/save', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/document/close */
  closeDocument: () =>
    apiCall('/revit/document/close', { method: 'POST' }),

  /** POST /revit/read_rvt */
  readRvt: (data: { filepath: string }) =>
    apiCall('/revit/read_rvt', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/write_rvt */
  writeRvt: (data: { filepath: string; elements: unknown[] }) =>
    apiCall('/revit/write_rvt', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/upload_rvt — Upload RVT file (multipart) */
  uploadRvt: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiCall('/revit/upload_rvt', {
      method: 'POST',
      body: formData,
      headers: {}, // Let browser set Content-Type for FormData
    });
  },

  /** GET /revit/elements */
  getElements: () => apiCall('/revit/elements'),

  /** GET /revit/elements/selected */
  getSelectedElements: () => apiCall('/revit/elements/selected'),

  /** GET /revit/elements/{element_id} */
  getElement: (elementId: string) => apiCall(`/revit/elements/${elementId}`),

  /** GET /revit/elements/{element_id}/parameters */
  getElementParameters: (elementId: string) =>
    apiCall(`/revit/elements/${elementId}/parameters`),

  /** POST /revit/elements/create/wall */
  createWall: (data: {
    start_point: number[];
    end_point: number[];
    height?: number;
    level?: string;
    wall_type?: string;
  }) => apiCall('/revit/elements/create/wall', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /revit/elements/create/floor */
  createFloor: (data: {
    boundary_points: number[][];
    level?: string;
    floor_type?: string;
  }) => apiCall('/revit/elements/create/floor', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /revit/elements/create/door */
  createDoor: (data: {
    host_wall_id: string;
    location_point: number[];
    family_type?: string;
    level?: string;
  }) => apiCall('/revit/elements/create/door', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /revit/elements/create/window */
  createWindow: (data: {
    host_wall_id: string;
    location_point: number[];
    family_type?: string;
    level?: string;
  }) => apiCall('/revit/elements/create/window', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /revit/elements/create/column */
  createColumn: (data: {
    location_point: number[];
    height?: number;
    level?: string;
    column_type?: string;
  }) => apiCall('/revit/elements/create/column', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /revit/elements/create/beam */
  createBeam: (data: {
    start_point: number[];
    end_point: number[];
    level?: string;
    beam_type?: string;
  }) => apiCall('/revit/elements/create/beam', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** POST /revit/elements/create/family */
  createFamily: (data: {
    family_name: string;
    category: string;
    location_point: number[];
    level?: string;
  }) => apiCall('/revit/elements/create/family', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /** PUT /revit/elements/{element_id}/parameters */
  updateElementParameters: (elementId: string, data: Record<string, unknown>) =>
    apiCall(`/revit/elements/${elementId}/parameters`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /** DELETE /revit/elements/{element_id} */
  deleteElement: (elementId: string) =>
    apiCall(`/revit/elements/${elementId}`, { method: 'DELETE' }),

  /** GET /revit/views */
  getViews: () => apiCall('/revit/views'),

  /** GET /revit/levels */
  getLevels: () => apiCall('/revit/levels'),

  /** GET /revit/grids */
  getGrids: () => apiCall('/revit/grids'),

  /** GET /revit/worksets */
  getWorksets: () => apiCall('/revit/worksets'),

  /** GET /revit/families/{category}/symbols */
  getFamilySymbols: (category: string) =>
    apiCall(`/revit/families/${category}/symbols`),

  /** POST /revit/families/load */
  loadFamily: (data: { family_path: string; category?: string }) =>
    apiCall('/revit/families/load', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/search/api/load */
  loadSearchApi: (data: { json_path: string }) =>
    apiCall('/revit/search/api/load', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /revit/search/api — AI-powered Revit API search */
  searchApi: (data: { query: string; context?: string }) =>
    apiCall('/revit/search/api', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /revit/search/online?q= */
  searchOnline: (query: string) =>
    apiCall(`/revit/search/online?q=${encodeURIComponent(query)}`),

  /** POST /revit/execute — Execute Revit command */
  execute: (data: { command: string; parameters?: Record<string, unknown> }) =>
    apiCall('/revit/execute', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// ─── AutoCAD API ────────────────────────────────────────────────────────────

export const autocadApi = {
  /** POST /autocad/connect */
  connect: (data: { visible?: boolean; force_new?: boolean } = {}) =>
    apiCall('/autocad/connect', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/disconnect */
  disconnect: () => apiCall('/autocad/disconnect', { method: 'POST' }),

  /** POST /autocad/read_dwg */
  readDwg: (data: { filepath: string }) =>
    apiCall('/autocad/read_dwg', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/write_dwg */
  writeDwg: (data: { filepath: string; entities: unknown[] }) =>
    apiCall('/autocad/write_dwg', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/draw_line */
  drawLine: (data: { start_point: number[]; end_point: number[]; layer?: string }) =>
    apiCall('/autocad/draw_line', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/draw_polyline */
  drawPolyline: (data: { points: number[][]; layer?: string }) =>
    apiCall('/autocad/draw_polyline', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/draw_circle */
  drawCircle: (data: { center: number[]; radius: number; layer?: string }) =>
    apiCall('/autocad/draw_circle', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/draw_text */
  drawText: (data: { point: number[]; text: string; height?: number; layer?: string }) =>
    apiCall('/autocad/draw_text', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /autocad/status */
  getStatus: () => apiCall('/autocad/status'),

  /** POST /autocad/save */
  save: (data: { filepath?: string }) =>
    apiCall('/autocad/save', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /autocad/upload_dwg — Upload DWG file (multipart) */
  uploadDwg: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiCall('/autocad/upload_dwg', {
      method: 'POST',
      body: formData,
      headers: {},
    });
  },

  /** DELETE /autocad/entity/{handle} */
  deleteEntity: (handle: string) =>
    apiCall(`/autocad/entity/${handle}`, { method: 'DELETE' }),

  /** PUT /autocad/entity/{handle} */
  updateEntity: (handle: string, data: Record<string, unknown>) =>
    apiCall(`/autocad/entity/${handle}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

// ─── Digital Twin API ───────────────────────────────────────────────────────

export const digitalTwinApi = {
  /** POST /digital-twin/convert */
  convert: (data: { source_file: string; target_format: string }) =>
    apiCall('/digital-twin/convert', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /digital-twin/history */
  getHistory: () => apiCall('/digital-twin/history'),

  /** POST /digital-twin/configure */
  configure: (data: Record<string, unknown>) =>
    apiCall('/digital-twin/configure', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /digital-twin/rollback/{version_id} */
  rollback: (versionId: string) =>
    apiCall(`/digital-twin/rollback/${versionId}`, { method: 'POST' }),

  /** GET /digital-twin/mappings */
  getMappings: () => apiCall('/digital-twin/mappings'),

  /** GET /digital-twin/status */
  getStatus: () => apiCall('/digital-twin/status'),

  /** POST /digital-twin/update_mapping */
  updateMapping: (data: Record<string, unknown>) =>
    apiCall('/digital-twin/update_mapping', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /digital-twin/config */
  getConfig: () => apiCall('/digital-twin/config'),

  /** PUT /digital-twin/config */
  setConfig: (data: Record<string, unknown>) =>
    apiCall('/digital-twin/config', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /** GET /digital-twin/download/{filename} */
  download: (filename: string) =>
    apiCall<Blob>(`/digital-twin/download/${filename}`),
};

// ─── Monitor API ────────────────────────────────────────────────────────────

export const monitorApi = {
  /** GET /monitor/health */
  getHealth: () => apiCall('/monitor/health', {}, API_BASE.replace('/v1', '')),

  /** GET /monitor/metrics (Prometheus format) */
  getMetrics: () =>
    apiCall<string>('/monitor/metrics', {}, API_BASE.replace('/v1', '')),

  /** GET /monitor/engine-status */
  getEngineStatus: () =>
    apiCall('/monitor/engine-status', {}, API_BASE.replace('/v1', '')),

  /** GET /monitor/agent-activity */
  getAgentActivity: (params?: { limit?: number }) =>
    apiCall(
      `/monitor/agent-activity${params?.limit ? `?limit=${params.limit}` : ''}`,
      {},
      API_BASE.replace('/v1', '')
    ),

  /** GET /monitor/security-alerts */
  getSecurityAlerts: (params?: { limit?: number; severity?: string }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.severity) query.set('severity', params.severity);
    const qs = query.toString();
    return apiCall(
      `/monitor/security-alerts${qs ? `?${qs}` : ''}`,
      {},
      API_BASE.replace('/v1', '')
    );
  },

  /** GET /monitor/alerts */
  getAlerts: () => apiCall('/monitor/alerts', {}, API_BASE.replace('/v1', '')),
};

// ─── Workflow API ───────────────────────────────────────────────────────────

export const workflowApi = {
  /** GET /workflow/status */
  getStatus: () => apiCall('/workflow/status'),

  /** POST /workflow/start */
  start: (data: { project_id: string; workflow_type: string; config?: Record<string, unknown> }) =>
    apiCall('/workflow/start', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /workflow/{workflow_id}/status */
  getWorkflowStatus: (workflowId: string) =>
    apiCall(`/workflow/${workflowId}/status`),

  /** POST /workflow/{workflow_id}/approve */
  approve: (workflowId: string, data?: { comment?: string }) =>
    apiCall(`/workflow/${workflowId}/approve`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  /** POST /workflow/{workflow_id}/reject */
  reject: (workflowId: string, data?: { reason?: string }) =>
    apiCall(`/workflow/${workflowId}/reject`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  /** GET /workflow/{workflow_id}/audit */
  getAudit: (workflowId: string) => apiCall(`/workflow/${workflowId}/audit`),
};

// ─── Memory API ─────────────────────────────────────────────────────────────

export const memoryApi = {
  /** GET /memory/status */
  getStatus: () => apiCall('/memory/status'),

  /** POST /memory/add */
  add: (data: { content: string; metadata?: Record<string, unknown> }) =>
    apiCall('/memory/add', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /memory/search */
  search: (data: { query: string; limit?: number }) =>
    apiCall('/memory/search', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /memory/all */
  getAll: () => apiCall('/memory/all'),

  /** DELETE /memory/{memory_id} */
  delete: (memoryId: string) =>
    apiCall(`/memory/${memoryId}`, { method: 'DELETE' }),

  /** GET /memory/{memory_id}/history */
  getHistory: (memoryId: string) => apiCall(`/memory/${memoryId}/history`),
};

// ─── V2 API (generative, BIM, IFC43, AR, webhooks, topology, graphrag) ──────

export const v2Api = {
  /** POST /generative/design */
  generativeDesign: (data: {
    room_polygon: Array<[number, number]>;
    detector_type: string;
    constraints?: Record<string, unknown>;
  }) =>
    apiCall('/generative/design', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** GET /bim/providers */
  getBimProviders: () => apiCall('/bim/providers', {}, API_V2_BASE),

  /** POST /bim/extract-rooms */
  extractBimRooms: (data: { source: string; provider?: string }) =>
    apiCall('/bim/extract-rooms', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** GET /bim/health */
  getBimHealth: () => apiCall('/bim/health', {}, API_V2_BASE),

  /** POST /ifc43/map-detector */
  mapDetector: (data: Record<string, unknown>) =>
    apiCall('/ifc43/map-detector', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /ifc43/map-project */
  mapProject: (data: Record<string, unknown>) =>
    apiCall('/ifc43/map-project', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /ar/export — Export AR metadata */
  exportAr: (data: { project_id: string; elements?: string[] }) =>
    apiCall('/ar/export', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /webhooks/subscribe */
  subscribeWebhook: (data: {
    url: string;
    event_types: string[];
    secret?: string;
  }) =>
    apiCall('/webhooks/subscribe', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** GET /webhooks/subscriptions */
  getWebhookSubscriptions: () =>
    apiCall('/webhooks/subscriptions', {}, API_V2_BASE),

  /** DELETE /webhooks/subscriptions/{sub_id} */
  deleteWebhookSubscription: (subId: string) =>
    apiCall(`/webhooks/subscriptions/${subId}`, { method: 'DELETE' }, API_V2_BASE),

  /** POST /webhooks/publish */
  publishWebhook: (data: { event_type: string; payload: unknown }) =>
    apiCall('/webhooks/publish', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /smoke-simulation/state */
  setSmokeSimulationState: (data: Record<string, unknown>) =>
    apiCall('/smoke-simulation/state', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /topology/element */
  addTopologyElement: (data: Record<string, unknown>) =>
    apiCall('/topology/element', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /topology/connection */
  addTopologyConnection: (data: Record<string, unknown>) =>
    apiCall('/topology/connection', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /topology/impact */
  analyzeTopologyImpact: (data: { element_id: string }) =>
    apiCall('/topology/impact', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** GET /topology/health */
  getTopologyHealth: () => apiCall('/topology/health', {}, API_V2_BASE),

  /** POST /graphrag/knowledge */
  ingestGraphragKnowledge: (data: Record<string, unknown>) =>
    apiCall('/graphrag/knowledge', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /graphrag/ask */
  askGraphrag: (data: { question: string; context?: string }) =>
    apiCall('/graphrag/ask', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** POST /graphrag/search */
  searchGraphrag: (data: { query: string; limit?: number }) =>
    apiCall('/graphrag/search', {
      method: 'POST',
      body: JSON.stringify(data),
    }, API_V2_BASE),

  /** GET /graphrag/health */
  getGraphragHealth: () => apiCall('/graphrag/health', {}, API_V2_BASE),

  /** GET /auth/csrf-token */
  getCsrfToken: () => apiCall('/auth/csrf-token', {}, API_V2_BASE),
};

// ─── Marine API ─────────────────────────────────────────────────────────────

export const marineApi = {
  /** GET /marine/standards */
  getStandards: () => apiCall('/marine/standards'),

  /** GET /marine/fire-classes */
  getFireClasses: () => apiCall('/marine/fire-classes'),

  /** POST /marine/ship/validate */
  validateShip: (data: Record<string, unknown>) =>
    apiCall('/marine/ship/validate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/ship/design */
  designShip: (data: Record<string, unknown>) =>
    apiCall('/marine/ship/design', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/zones/divide */
  divideZones: (data: Record<string, unknown>) =>
    apiCall('/marine/zones/divide', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/extinguishing/design */
  designExtinguishing: (data: Record<string, unknown>) =>
    apiCall('/marine/extinguishing/design', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/alarm-logic/generate */
  generateAlarmLogic: (data: Record<string, unknown>) =>
    apiCall('/marine/alarm-logic/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/detection/design */
  designDetection: (data: Record<string, unknown>) =>
    apiCall('/marine/detection/design', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/divisions/generate */
  generateDivisions: (data: Record<string, unknown>) =>
    apiCall('/marine/divisions/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/power/design */
  designPower: (data: Record<string, unknown>) =>
    apiCall('/marine/power/design', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/integrations/scada */
  integrateScada: (data: Record<string, unknown>) =>
    apiCall('/marine/integrations/scada', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/integrations/etap */
  integrateEtap: (data: Record<string, unknown>) =>
    apiCall('/marine/integrations/etap', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/integrations/dxf */
  exportDxf: (data: Record<string, unknown>) =>
    apiCall('/marine/integrations/dxf', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /marine/integrations/revit */
  exportRevit: (data: Record<string, unknown>) =>
    apiCall('/marine/integrations/revit', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// ─── API Keys (Admin) ───────────────────────────────────────────────────────

export const apiKeysApi = {
  /** GET /admin/keys */
  list: () => apiCall('/admin/keys'),

  /** POST /admin/keys */
  create: (data: { role: string; description?: string; expires_at?: string }) =>
    apiCall('/admin/keys', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** DELETE /admin/keys/{key_hash} */
  delete: (keyHash: string) =>
    apiCall(`/admin/keys/${keyHash}`, { method: 'DELETE' }),

  /** PUT /admin/keys/{key_hash} */
  update: (keyHash: string, data: { role?: string; description?: string }) =>
    apiCall(`/admin/keys/${keyHash}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /** GET /admin/keys/roles */
  getRoles: () => apiCall('/admin/keys/roles'),
};

// ─── Exports API ────────────────────────────────────────────────────────────

export const exportsApi = {
  /** GET /projects/{project_id}/export/dxf */
  exportDxf: (projectId: string) =>
    apiCall<Blob>(`/projects/${projectId}/export/dxf`),

  /** GET /projects/{project_id}/export/revit */
  exportRevit: (projectId: string) =>
    apiCall<Blob>(`/projects/${projectId}/export/revit`),

  /** GET /projects/{project_id}/export/ifc */
  exportIfc: (projectId: string, version: string = 'IFC4') =>
    apiCall<Blob>(`/projects/${projectId}/export/ifc?version=${version}`),
};

// ─── DWG Parser API ─────────────────────────────────────────────────────────

export const dwgApi = {
  /** POST /parse-dwg — Upload and parse DWG/DXF file */
  parseDwg: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiCall('/parse-dwg', {
      method: 'POST',
      body: formData,
      headers: {},
    });
  },
};

// ─── Analyze API ────────────────────────────────────────────────────────────

export const analyzeApi = {
  /** POST /analyze/battery */
  analyzeBattery: (data: Record<string, unknown>) =>
    apiCall('/analyze/battery', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** POST /analyze/voltage */
  analyzeVoltage: (data: Record<string, unknown>) =>
    apiCall('/analyze/voltage', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// ─── Health & Cache API ─────────────────────────────────────────────────────

export const systemApi = {
  /** GET /health */
  health: () => apiCall('/health', {}, '/api'),

  /** GET /health/statistics */
  healthStatistics: () => apiCall('/health/statistics', {}, '/api'),

  /** GET /reports/statistics */
  reportsStatistics: () => apiCall('/reports/statistics', {}, '/api'),

  /** POST /cache/clear */
  clearCache: () =>
    apiCall('/cache/clear', { method: 'POST' }),

  /** GET /cache/stats */
  cacheStats: () => apiCall('/cache/stats'),
};

// ─── Unified Export ─────────────────────────────────────────────────────────

export const fullApi = {
  // Core CRUD (re-export from existing api.ts for backward compat)
  core: coreApi,
  digitalTwin: digitalTwinApiClient,

  // All API modules
  qomn: qomnApi,
  facp: facpApi,
  environment: environmentApi,
  revit: revitApi,
  autocad: autocadApi,
  digitalTwinLegacy: digitalTwinApi,
  monitor: monitorApi,
  workflow: workflowApi,
  memory: memoryApi,
  v2: v2Api,
  marine: marineApi,
  apiKeys: apiKeysApi,
  exports: exportsApi,
  dwg: dwgApi,
  analyze: analyzeApi,
  system: systemApi,
};

export default fullApi;
