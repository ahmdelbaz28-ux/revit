/**
 * @file store.ts
 * @description Shared types for the application state store.
 *
 * V183 FIX: This file was out of sync with src/store/simpleStore.ts (the
 * actual implementation). The audit report (operator-provided) flagged:
 *   - faults: string[] here vs {id,type,timestamp}[] in simpleStore
 *   - connectionStatus missing 'connecting' state
 *   - errors/errorLog/selectedElementId/selectedElement missing entirely
 *
 * Fixed by aligning this type file with the actual simpleStore.ts
 * implementation. simpleStore.ts is the source of truth (it's the file
 * that's imported everywhere).
 */

export interface AppFault {
  id: string;
  type: string;
  timestamp: number;
}

export interface AppError {
  id: string;
  message: string;
  timestamp: number;
  severity?: 'low' | 'medium' | 'high' | 'critical';
}

export interface AppState {
  /** Current UI theme */
  theme: 'dark' | 'light' | 'blue';

  /** Active faults (full fault objects, not just IDs) */
  faults: AppFault[];

  /** Help sidebar visibility state */
  helpOpen: boolean;

  /** Live telemetry data (simulated or real) */
  liveData: {
    voltage: number;
    current: number;
    frequency: number;
  };

  /** SCADA Event log messages */
  eventLogs: string[];

  /** Data source mode: 'mock' for simulation, 'live' for real data */
  dataMode: 'mock' | 'live';

  /** Connection status to the data source (includes 'connecting' transient state) */
  connectionStatus: 'connected' | 'disconnected' | 'connecting';

  /** Error log (kept for backward compat — same as `errors`) */
  errorLog: AppError[];

  /** Primary error array (use this in new code; `errorLog` is an alias) */
  errors: AppError[];

  /** Selected element ID (primary field — use this in new code) */
  selectedElementId: string | null;

  /** Selected element (legacy alias for selectedElementId — kept for backward compat) */
  selectedElement: string | null;

  /** Active palette tool type (used by Fire Alarm Designer canvas) */
  activePaletteType: string | null;

  /** Voice control active state */
  voiceActive: boolean;
}
