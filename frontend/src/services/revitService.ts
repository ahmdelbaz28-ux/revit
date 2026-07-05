/**
 * revitService.ts — Revit API Service
 *
 * V140 Phase 6: Comprehensive Revit service covering ALL 32 endpoints.
 */
import { revitApi } from "./fullApi";

export const revitService = {
	// ─── Connection ───────────────────────────────────────────────────────
	/** POST /revit/connect */
	connect: (visible?: boolean, force_new?: boolean) =>
		revitApi.connect({ visible, force_new }),

	/** POST /revit/disconnect */
	disconnect: () => revitApi.disconnect(),

	/** GET /revit/status */
	getStatus: () => revitApi.getStatus(),

	// ─── Document Operations ─────────────────────────────────────────────
	/** POST /revit/document/open */
	openDocument: (filepath: string) => revitApi.openDocument({ filepath }),

	/** POST /revit/document/save */
	saveDocument: (filepath?: string) => revitApi.saveDocument({ filepath }),

	/** POST /revit/document/close */
	closeDocument: () => revitApi.closeDocument(),

	// ─── File Operations ─────────────────────────────────────────────────
	/** POST /revit/read_rvt */
	readRvt: (filepath: string) => revitApi.readRvt({ filepath }),

	/** POST /revit/write_rvt */
	writeRvt: (filepath: string, elements: unknown[]) =>
		revitApi.writeRvt({ filepath, elements }),

	/** POST /revit/upload_rvt */
	uploadRvt: (file: File) => revitApi.uploadRvt(file),

	// ─── Element Queries ─────────────────────────────────────────────────
	/** GET /revit/elements */
	getElements: () => revitApi.getElements(),

	/** GET /revit/elements/selected */
	getSelectedElements: () => revitApi.getSelectedElements(),

	/** GET /revit/elements/{element_id} */
	getElement: (elementId: string) => revitApi.getElement(elementId),

	/** GET /revit/elements/{element_id}/parameters */
	getElementParameters: (elementId: string) =>
		revitApi.getElementParameters(elementId),

	// ─── Element Creation ────────────────────────────────────────────────
	/** POST /revit/elements/create/wall */
	createWall: (
		startPoint: number[],
		endPoint: number[],
		height?: number,
		level?: string,
		wallType?: string,
	) =>
		revitApi.createWall({
			start_point: startPoint,
			end_point: endPoint,
			height,
			level,
			wall_type: wallType,
		}),

	/** POST /revit/elements/create/floor */
	createFloor: (
		boundaryPoints: number[][],
		level?: string,
		floorType?: string,
	) =>
		revitApi.createFloor({
			boundary_points: boundaryPoints,
			level,
			floor_type: floorType,
		}),

	/** POST /revit/elements/create/door */
	createDoor: (
		hostWallId: string,
		locationPoint: number[],
		familyType?: string,
		level?: string,
	) =>
		revitApi.createDoor({
			host_wall_id: hostWallId,
			location_point: locationPoint,
			family_type: familyType,
			level,
		}),

	/** POST /revit/elements/create/window */
	createWindow: (
		hostWallId: string,
		locationPoint: number[],
		familyType?: string,
		level?: string,
	) =>
		revitApi.createWindow({
			host_wall_id: hostWallId,
			location_point: locationPoint,
			family_type: familyType,
			level,
		}),

	/** POST /revit/elements/create/column */
	createColumn: (
		locationPoint: number[],
		height?: number,
		level?: string,
		columnType?: string,
	) =>
		revitApi.createColumn({
			location_point: locationPoint,
			height,
			level,
			column_type: columnType,
		}),

	/** POST /revit/elements/create/beam */
	createBeam: (
		startPoint: number[],
		endPoint: number[],
		level?: string,
		beamType?: string,
	) =>
		revitApi.createBeam({
			start_point: startPoint,
			end_point: endPoint,
			level,
			beam_type: beamType,
		}),

	/** POST /revit/elements/create/family */
	createFamily: (
		familyName: string,
		category: string,
		locationPoint: number[],
		level?: string,
	) =>
		revitApi.createFamily({
			family_name: familyName,
			category,
			location_point: locationPoint,
			level,
		}),

	// ─── Element Modification ────────────────────────────────────────────
	/** PUT /revit/elements/{element_id}/parameters */
	updateElementParameters: (
		elementId: string,
		params: Record<string, unknown>,
	) => revitApi.updateElementParameters(elementId, params),

	/** DELETE /revit/elements/{element_id} */
	deleteElement: (elementId: string) => revitApi.deleteElement(elementId),

	// ─── Project Structure ───────────────────────────────────────────────
	/** GET /revit/views */
	getViews: () => revitApi.getViews(),

	/** GET /revit/levels */
	getLevels: () => revitApi.getLevels(),

	/** GET /revit/grids */
	getGrids: () => revitApi.getGrids(),

	/** GET /revit/worksets */
	getWorksets: () => revitApi.getWorksets(),

	// ─── Families ────────────────────────────────────────────────────────
	/** GET /revit/families/{category}/symbols */
	getFamilySymbols: (category: string) => revitApi.getFamilySymbols(category),

	/** POST /revit/families/load */
	loadFamily: (familyPath: string, category?: string) =>
		revitApi.loadFamily({ family_path: familyPath, category }),

	// ─── Search & AI ─────────────────────────────────────────────────────
	/** POST /revit/search/api/load */
	loadSearchApi: (jsonPath: string) =>
		revitApi.loadSearchApi({ json_path: jsonPath }),

	/** POST /revit/search/api — AI-powered Revit API search */
	searchApi: (query: string, context?: string) =>
		revitApi.searchApi({ query, context }),

	/** GET /revit/search/online?q= */
	searchOnline: (query: string) => revitApi.searchOnline(query),

	// ─── Execute ─────────────────────────────────────────────────────────
	/** POST /revit/execute — Execute arbitrary Revit command */
	execute: (command: string, parameters?: Record<string, unknown>) =>
		revitApi.execute({ command, parameters }),
};

export default revitService;
