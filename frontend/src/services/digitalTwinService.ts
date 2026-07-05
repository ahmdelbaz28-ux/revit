/**
 * digitalTwinService.ts — Digital Twin API Service
 *
 * V140 Phase 6: Comprehensive Digital Twin service covering ALL 10 endpoints.
 */
import { digitalTwinApi } from "./fullApi";

export interface ConversionResult {
	success: boolean;
	source_file: string;
	target_file: string;
	conversion_type: string;
	elements_count: number;
	duration_seconds: number;
}

export interface VersionInfo {
	version_id: string;
	timestamp: string;
	source_file: string;
	target_file: string;
	conversion_type: "autocad_to_revit" | "revit_to_autocad";
	elements_count: number;
	status: "success" | "partial" | "failed";
}

export const digitalTwinService = {
	/** POST /digital-twin/convert — Bidirectional conversion */
	convert: (sourceFile: string, targetFormat: string) =>
		digitalTwinApi.convert({
			source_file: sourceFile,
			target_format: targetFormat,
		}),

	/** GET /digital-twin/history — Get conversion history */
	getHistory: () => digitalTwinApi.getHistory() as Promise<VersionInfo[]>,

	/** POST /digital-twin/configure — Update conversion config */
	configure: (config: Record<string, unknown>) =>
		digitalTwinApi.configure(config),

	/** POST /digital-twin/rollback/{version_id} — Rollback to version */
	rollback: (versionId: string) => digitalTwinApi.rollback(versionId),

	/** GET /digital-twin/mappings — Get available mappings */
	getMappings: () => digitalTwinApi.getMappings(),

	/** GET /digital-twin/status — Get service status */
	getStatus: () => digitalTwinApi.getStatus(),

	/** POST /digital-twin/update_mapping — Update single mapping */
	updateMapping: (mapping: Record<string, unknown>) =>
		digitalTwinApi.updateMapping(mapping),

	/** GET /digital-twin/config — Get current config */
	getConfig: () => digitalTwinApi.getConfig(),

	/** PUT /digital-twin/config — Set config */
	setConfig: (config: Record<string, unknown>) =>
		digitalTwinApi.setConfig(config),

	/** GET /digital-twin/download/{filename} — Download converted file */
	download: (filename: string) => digitalTwinApi.download(filename),
};

export default digitalTwinService;
