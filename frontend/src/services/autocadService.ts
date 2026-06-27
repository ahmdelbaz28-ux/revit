/**
 * autocadService.ts — AutoCAD API Service
 *
 * V140 Phase 6: Comprehensive AutoCAD service covering ALL 13 endpoints.
 * Uses the unified apiCall helper from fullApi.ts.
 */
import { autocadApi } from './fullApi';

export const autocadService = {
  /** POST /autocad/connect — Connect to running AutoCAD instance */
  connect: (visible: boolean = true, force_new: boolean = false) =>
    autocadApi.connect({ visible, force_new }),

  /** POST /autocad/disconnect — Disconnect from AutoCAD */
  disconnect: () => autocadApi.disconnect(),

  /** POST /autocad/read_dwg — Read DWG file */
  readDwg: (filepath: string) => autocadApi.readDwg({ filepath }),

  /** POST /autocad/write_dwg — Write DWG file */
  writeDwg: (filepath: string, entities: unknown[]) =>
    autocadApi.writeDwg({ filepath, entities }),

  /** POST /autocad/draw_line — Draw a line */
  drawLine: (start: number[], end: number[], layer?: string) =>
    autocadApi.drawLine({ start_point: start, end_point: end, layer }),

  /** POST /autocad/draw_polyline — Draw a polyline */
  drawPolyline: (points: number[][], layer?: string) =>
    autocadApi.drawPolyline({ points, layer }),

  /** POST /autocad/draw_circle — Draw a circle */
  drawCircle: (center: number[], radius: number, layer?: string) =>
    autocadApi.drawCircle({ center, radius, layer }),

  /** POST /autocad/draw_text — Draw text */
  drawText: (point: number[], text: string, height?: number, layer?: string) =>
    autocadApi.drawText({ point, text, height, layer }),

  /** GET /autocad/status — Get connection status */
  getStatus: () => autocadApi.getStatus(),

  /** POST /autocad/save — Save document */
  save: (filepath?: string) => autocadApi.save({ filepath }),

  /** POST /autocad/upload_dwg — Upload & read DWG file */
  uploadDwg: (file: File) => autocadApi.uploadDwg(file),

  /** DELETE /autocad/entity/{handle} — Delete entity by handle */
  deleteEntity: (handle: string) => autocadApi.deleteEntity(handle),

  /** PUT /autocad/entity/{handle} — Update entity by handle */
  updateEntity: (handle: string, data: Record<string, unknown>) =>
    autocadApi.updateEntity(handle, data),
};

export default autocadService;
