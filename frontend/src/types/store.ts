/**
 * @file store.ts
 * @description Shared types for the application state store.
 */

export interface AppState {
  /** Current UI theme */
  theme: 'dark' | 'light' | 'blue';
  
  /** Array of active fault IDs */
  faults: string[];
  
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
  
  /** Connection status to the data source */
  connectionStatus: 'connected' | 'disconnected';
}
