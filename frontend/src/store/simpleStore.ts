
import { useEffect, useRef, useState } from "react";

// --- Types ---
export type DeviceType =
        | "GENERATOR"
        | "BATTERY"
        | "LOAD"
        | "PANEL"
        | "SENSOR_MOTION"
        | "SENSOR_SMOKE"
        | "CAMERA"
        | "SPEAKER";

export interface Device {
        id: string;
        type: DeviceType;
        x: number;
        y: number;
        load: number; // Amperes
        voltage: number;
}

export interface Connection {
        id: string;
        fromId: string;
        toId: string;
        current: number; // Calculated current
        isOverloaded: boolean;
}

export interface LogEntry {
        id: string;
        message: string;
        type: "info" | "warning" | "error" | "success";
        timestamp: number;
}

// --- Additional Interfaces ---
export interface AppError {
        id: string;
        message: string;
        severity: "info" | "warning" | "critical";
        timestamp: number;
        relatedElementId?: string;
        elementId?: string;
}
export interface CanvasElement {
        id: string;
        type: string;
        x: number;
        y: number;
        properties?: Record<string, unknown>;
        from?: string;
        to?: string;
        voltage?: number;
        load?: number;
}

export interface AppState {
        theme: "dark" | "light" | "blue";
        devices: Device[];
        connections: Connection[];
        errorLog: AppError[];
        errors: AppError[];
        selectedElementId: string | null;
        selectedElement: string | null;
        activePaletteType: DeviceType | null;
        isSidebarOpen: boolean;
        canvasElements: CanvasElement[];
        helpOpen: boolean;
        eventLogs: LogEntry[];
        dataMode: "live" | "simulation" | "demo" | "mock";  // NOSONAR: typescript:S4323
        liveData: Record<string, unknown>;
        connectionStatus: "connected" | "disconnected" | "connecting";  // NOSONAR: typescript:S4323
        voiceActive: boolean;
        faults: Array<{ id: string; type: string; timestamp: number }>;
        setDataMode: (mode: "live" | "simulation" | "demo" | "mock") => void;
        toggleHelp: () => void;
        addLog: (log: Omit<LogEntry, "id" | "timestamp">) => void;
        addElement: (element: Omit<CanvasElement, "id">) => void;
        removeElement: (id: string) => void;
        pushError: (message: string) => void;
        setSelectedElement: (id: string | null) => void;
        removeFault: (id: string | { id: string }) => void;
        addFault: (fault: { type: string }) => void;
        updateLiveData: (data: Record<string, unknown>) => void;
        setConnectionStatus: (
                status: "connected" | "disconnected" | "connecting",
        ) => void;
        setVoiceActive: (active: boolean) => void;
}

// Unique ID generator — uses crypto.randomUUID() for collision-free IDs.
// Previous bug: Date.now() caused ID collisions when multiple entities
// were created within the same millisecond (batch operations, rapid clicks).
const uid = () => crypto.randomUUID();

// Maximum array sizes to prevent unbounded memory growth in localStorage.
const MAX_LOG_ENTRIES = 500;
const MAX_ERROR_ENTRIES = 200;
const MAX_FAULT_ENTRIES = 100;

// Method stubs for AppState — these are placeholder functions that are
// immediately overwritten by the `actions` object below. They exist only
// to satisfy TypeScript's type contract on the AppState interface.
// Previously, full method implementations were duplicated here AND in `actions`,
// which was a maintenance hazard (bugs could be fixed in one place but not the other).
const _stub = () => {
        /* placeholder — real implementation in `actions` */
};

const initialState: AppState = {
        theme: "dark",
        devices: [],
        connections: [],
        errorLog: [],
        errors: [],
        selectedElementId: null,
        selectedElement: null,
        activePaletteType: null,
        isSidebarOpen: true,
        canvasElements: [],
        helpOpen: false,
        eventLogs: [],
        dataMode: "demo",
        liveData: {},
        connectionStatus: "disconnected",
        voiceActive: false,
        faults: [],
        // Stub methods — real implementations are in `actions` below
        setDataMode: () => _stub(),
        toggleHelp: () => _stub(),
        addLog: () => _stub(),
        addElement: () => _stub(),
        removeElement: () => _stub(),
        pushError: () => _stub(),
        setSelectedElement: () => _stub(),
        removeFault: () => _stub(),
        addFault: () => _stub(),
        updateLiveData: () => _stub(),
        setConnectionStatus: () => _stub(),
        setVoiceActive: () => _stub(),
};

// --- State Management Logic ---
let state: AppState = { ...initialState };
const listeners = new Set<(s: AppState) => void>();

// Load from LocalStorage on init — CRITICAL: only restore serializable data fields,
// NOT function references (JSON.parse destroys them, and the spread would overwrite
// the working function refs from initialState with undefined).
const SERIALIZABLE_KEYS: (keyof AppState)[] = [
        "theme",
        "devices",
        "connections",
        "errorLog",
        "errors",
        "selectedElementId",
        "selectedElement",
        "activePaletteType",
        "isSidebarOpen",
        "canvasElements",
        "helpOpen",
        "eventLogs",
        "dataMode",
        "liveData",
        "connectionStatus",
        "voiceActive",
        "faults",
];

// V250 FIX: Wrap localStorage access in try/catch. In sandboxed iframes or
// when cookies are blocked, localStorage.getItem() throws SecurityError.
// Without this guard, the entire app crashes at boot (module-load time).
let savedState: string | null = null;
try {
        savedState = localStorage.getItem("nexus_project_state");
} catch (e) {
        // localStorage unavailable (sandboxed iframe, cookies blocked, etc.)
        // App will use initialState — non-fatal.
        console.warn("localStorage unavailable, using default state:", e);
}
if (savedState) {
        try {
                const parsed = JSON.parse(savedState);
                const safeUpdates: Partial<AppState> = {};
                for (const key of SERIALIZABLE_KEYS) {
                        if (key in parsed) {
                                (safeUpdates as Record<string, unknown>)[key] = parsed[key];
                        }
                }
                state = { ...initialState, ...safeUpdates };
        } catch (e) {
                console.error("Failed to load state", e);
        }
}

export const setState = (
        nextState: Partial<AppState> | ((s: AppState) => Partial<AppState>),
) => {
        const updates =
                typeof nextState === "function" ? nextState(state) : nextState;
        state = { ...state, ...updates };

        // Auto-save to LocalStorage — only save serializable keys, NOT function references
        const serializable: Record<string, unknown> = {};
        for (const key of SERIALIZABLE_KEYS) {
                serializable[key] = state[key];
        }
        try {
                localStorage.setItem("nexus_project_state", JSON.stringify(serializable));
        } catch {
                console.warn("Failed to persist state to localStorage");
        }

        listeners.forEach((listener) => listener(state));
};

export const subscribe = (listener: (s: AppState) => void) => {
        listeners.add(listener);
        return () => {
                listeners.delete(listener);
        };
};

export const getState = (): AppState => state;

export const useStore = <T>(selector: (s: AppState) => T): T => {
        const [slice, setSlice] = useState(selector(state));
        // Store the selector in a ref so the useEffect doesn't re-subscribe
        // on every render. Previous bug: selector was a dependency of useEffect,
        // and since arrow functions create new references each render, this caused
        // subscribe/unsubscribe churn on every render.
        const selectorRef = useRef(selector);
        selectorRef.current = selector;

        useEffect(() => {
                const unsubscribe = subscribe((newState) => {
                        setSlice(selectorRef.current(newState));
                });
                return unsubscribe;
        }, []);
        return slice;
};

// --- Actions ---
export const actions = {
        setTheme: (theme: "dark" | "light" | "blue") => setState({ theme }),
        toggleSidebar: () => setState((s) => ({ isSidebarOpen: !s.isSidebarOpen })),
        selectElement: (id: string | null) => setState({ selectedElementId: id }),
        setSelectedElement: (id: string | null) =>
                setState({ selectedElementId: id, selectedElement: id }),
        setActivePaletteType: (type: DeviceType | null) =>
                setState({ activePaletteType: type }),
        setDataMode: (mode: "live" | "simulation" | "demo" | "mock") =>
                setState({ dataMode: mode }),
        toggleHelp: () => setState((s) => ({ helpOpen: !s.helpOpen })),

        addDevice: (device: Omit<Device, "id">) => {
                const newDevice: Device = { ...device, id: uid() };
                setState((s) => ({ devices: [...s.devices, newDevice] }));
                return newDevice.id;
        },

        updateDevicePosition: (id: string, x: number, y: number) => {
                setState((s) => ({
                        devices: s.devices.map((d) => (d.id === id ? { ...d, x, y } : d)),
                }));
        },

        deleteDevice: (id: string) => {
                setState((s) => ({
                        devices: s.devices.filter((d) => d.id !== id),
                        connections: s.connections.filter(
                                (c) => c.fromId !== id && c.toId !== id,
                        ),
                }));
        },

        addConnection: (fromId: string, toId: string) => {
                setState((s) => {
                        if (
                                s.connections.some(
                                        (c) =>
                                                (c.fromId === fromId && c.toId === toId) ||
                                                (c.fromId === toId && c.toId === fromId),
                                )
                        ) {
                                return s;
                        }

                        const fromDev = s.devices.find((d) => d.id === fromId);
                        const toDev = s.devices.find((d) => d.id === toId);

                        if (!fromDev || !toDev) return s;

                        const combinedLoad = (fromDev.load + toDev.load) / 2;
                        const isOverloaded = combinedLoad > 200;

                        const newConn: Connection = {
                                id: uid(),
                                fromId,
                                toId,
                                current: combinedLoad,
                                isOverloaded,
                        };

                        if (isOverloaded) {
                                actions.addError({
                                        message: `Overload Detected on connection ${newConn.id} (${combinedLoad.toFixed(1)}A)`,
                                        severity: "critical",
                                        relatedElementId: newConn.id,
                                });
                        }

                        return { connections: [...s.connections, newConn] };
                });
        },

        addError: (error: Omit<AppError, "id" | "timestamp">) => {
                const now = Date.now();
                const newError: AppError = {
                        ...error,
                        id: uid(),
                        timestamp: now,
                };
                // V185 FIX: errorLog is now an alias for errors (single source of truth).
                // Was duplicated, causing potential drift if one was updated without the other.
                setState((s) => ({
                        errors: [newError, ...s.errors].slice(0, MAX_ERROR_ENTRIES),
                        errorLog: [newError, ...s.errors].slice(0, MAX_ERROR_ENTRIES),
                }));
        },

        pushError: (message: string | { message: string }) => {
                const now = Date.now();
                const msg = typeof message === "string" ? message : message.message;
                const error: AppError = {
                        id: uid(),
                        message: msg,
                        severity: "critical",
                        timestamp: now,
                };
                // V185 FIX: errorLog = errors (alias, no more drift)
                setState((s) => ({
                        errors: [error, ...s.errors].slice(0, MAX_ERROR_ENTRIES),
                        errorLog: [error, ...s.errors].slice(0, MAX_ERROR_ENTRIES),
                }));
        },

        addElement: (element: Omit<CanvasElement, "id"> | CanvasElement) => {
                const newElement: CanvasElement =
                        "id" in element ? element : { ...element, id: uid() };
                setState((s) => ({ canvasElements: [...s.canvasElements, newElement] }));
        },

        removeElement: (id: string) =>
                setState((s) => ({
                        canvasElements: s.canvasElements.filter((el) => el.id !== id),
                })),

        addLog: (log: string | Omit<LogEntry, "id" | "timestamp">) => {
                const now = Date.now();
                const newLog: LogEntry =
                        typeof log === "string"
                                ? { id: uid(), message: log, type: "info", timestamp: now }
                                : { ...log, id: uid(), timestamp: now };
                setState((s) => ({
                        eventLogs: [newLog, ...s.eventLogs].slice(0, MAX_LOG_ENTRIES),
                }));
        },

        clearErrors: () => setState({ errors: [], errorLog: [] }),

        resetProject: () => {
                setState({
                        devices: [],
                        connections: [],
                        errors: [],
                        errorLog: [],
                        selectedElementId: null,
                        activePaletteType: null,
                });
                localStorage.removeItem("nexus_project_state");
        },

        addFault: (fault: string | { type: string }) => {
                const now = Date.now();
                const faultType = typeof fault === "string" ? fault : fault.type;
                const newFault = { id: uid(), type: faultType, timestamp: now };
                setState((s) => ({
                        faults: [...s.faults, newFault].slice(0, MAX_FAULT_ENTRIES),
                }));
        },

        removeFault: (id: string | { id: string }) => {
                const faultId = typeof id === "string" ? id : id.id;
                setState((s) => ({ faults: s.faults.filter((f) => f.id !== faultId) }));
        },

        updateLiveData: (data: Record<string, unknown>) =>
                setState((s) => ({ liveData: { ...s.liveData, ...data } })),

        setConnectionStatus: (status: "connected" | "disconnected" | "connecting") =>
                setState({ connectionStatus: status }),

        setVoiceActive: (active: boolean) => setState({ voiceActive: active }),
};
