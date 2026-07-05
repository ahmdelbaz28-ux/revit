/**
 * UDM (UniversalDataModel) Types
 *
 * These types correspond to System B — the UDM Elements API.
 * Backend: udm_elements.db, routers: elements.py, connections_v2.py, conflicts.py
 * Field naming: snake_case (matching Python/DB conventions)
 *
 * Do NOT confuse with the Digital Twin API types in digitalTwinApi.ts
 * which use camelCase fields and connect to digital_twin.db.
 */

// ===== API Response Wrapper =====

export interface UdmApiResponse<T> {
	success: boolean;
	data?: T;
	error?: string;
	message?: string;
}

// ===== Paginated Data Wrapper =====

export interface UdmPaginatedData<T> {
	items: T[];
	total: number;
	page: number;
	page_size: number;
	total_pages: number;
}

// ===== Point / Geometry =====

export interface Point3D {
	x: number;
	y: number;
	z: number;
}

export interface ElementGeometry {
	points: Point3D[];
	polyline_closed: boolean;
	area: number;
	perimeter: number;
}

export interface ElementGeometryCreate {
	points: Point3D[];
	polyline_closed?: boolean;
}

// ===== Element =====

export interface ElementProperties {
	element_type: string; // wall, door, window, room, equipment, mechanical, electrical, unknown
	name: string;
	description?: string;
	material?: string;
	fire_rating?: string;
	height?: number;
	width?: number;
	load_bearing: boolean;
	layer?: string;
	revit_category?: string;
}

export interface ElementPropertiesCreate {
	element_type: string;
	name: string;
	description?: string;
	material?: string;
	fire_rating?: string;
	height?: number;
	width?: number;
	load_bearing?: boolean;
	layer?: string;
	revit_category?: string;
}

export interface Element {
	element_id: string;
	properties: ElementProperties | null;
	geometry: ElementGeometry | null;
	relationships: Array<Record<string, unknown>>;
	version: number;
	is_deleted: boolean;
	created_timestamp: string | null;
	last_modified_timestamp: string | null;
	last_modified_by: string | null;
	source_file: string | null;
	autocad_handle: string | null;
	revit_element_id: number | null;
	project_id: string | null;
}

export interface ElementCreate {
	properties: ElementPropertiesCreate;
	geometry?: ElementGeometryCreate;
	source_file?: string;
	last_modified_by?: string;
	autocad_handle?: string;
	revit_element_id?: number;
	project_id?: string;
}

export interface ElementUpdate {
	properties?: Record<string, unknown>;
	geometry?: Record<string, unknown>;
	source_file?: string;
	last_modified_by?: string;
	is_deleted?: boolean;
}

export interface ElementsListParams {
	element_type?: string;
	project_id?: string;
	is_deleted?: boolean;
	page?: number;
	page_size?: number;
	sort_by?: string;
	sort_order?: string;
}

// ===== Project =====

export interface UdmProject {
	project_id: string;
	name: string;
	description?: string;
	status: string;
	metadata?: Record<string, unknown>;
	element_count: number;
	created_timestamp: string | null;
	last_modified_timestamp: string | null;
}

export interface ProjectCreate {
	name: string;
	description?: string;
	status?: string;
	metadata?: Record<string, unknown>;
}

export interface ProjectUpdate {
	name?: string;
	description?: string;
	status?: string;
	metadata?: Record<string, unknown>;
}

// ===== Connection =====

export interface UdmConnection {
	connection_id: string;
	from_element_id: string;
	to_element_id: string;
	relationship_type: string;
	is_parametric: boolean;
	metadata?: Record<string, unknown> | null;
}

export interface ConnectionCreate {
	from_element_id: string;
	to_element_id: string;
	relationship_type: string;
	is_parametric?: boolean;
	metadata?: Record<string, unknown>;
}

export interface ConnectionsListParams {
	project_id?: string;
	element_id?: string;
	relationship_type?: string;
	page?: number;
	page_size?: number;
}

// ===== Conflict =====

export interface Conflict {
	conflict_id: string;
	element_id: string;
	conflict_type: string;
	timestamp: string | null;
	source_a: string | null;
	source_b: string | null;
	change_a?: Record<string, unknown> | null;
	change_b?: Record<string, unknown> | null;
	resolution?: Record<string, unknown> | null;
	resolved: boolean;
}

export interface ConflictsListParams {
	resolved?: boolean;
	conflict_type?: string;
	page?: number;
	page_size?: number;
}

// ===== Statistics =====

export interface Statistics {
	total_elements: number;
	deleted_elements: number;
	active_elements: number;
	total_projects: number;
	active_projects: number;
	total_connections: number;
	total_conflicts: number;
	unresolved_conflicts: number;
	pending_autocad_to_revit: number;
	pending_revit_to_autocad: number;
	database_version: number;
	last_sync: string | null;
}

// ===== Health =====

export interface HealthStatus {
	status: "ok" | "degraded" | "error";
	version: string;
	uptime: number;
	database: "connected" | "disconnected";
	timestamp: string;
	// Legacy fields kept for backward compatibility
	uptime_seconds?: number;
	core_modules?: string;
	total_elements?: number;
	total_projects?: number;
	warning?: string;
}
