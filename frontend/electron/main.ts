import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync, ChildProcess } from "node:child_process";
import http from "node:http";
import {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
} from "electron";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
// DIST is at the project root level (sibling of electron/ directory)
const DIST = path.resolve(ROOT, "..", "dist");
// When running inside asar, unpacked backend files are in the resources dir
const RESOURCES = process.resourcesPath || path.resolve(ROOT, "..", "..");

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

// FIX v2: parse and validate the port (was raw string with no validation)
function parsePort(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n) || n < 1 || n > 65535) {
    console.warn(`[Config] Invalid port '${value}', falling back to ${fallback}`);
    return fallback;
  }
  return n;
}

const PYTHON_BACKEND_PORT = parsePort(process.env.FIREAI_BACKEND_PORT, 8000);
const PYTHON_BACKEND_URL = `http://localhost:${PYTHON_BACKEND_PORT}`;

// FIX v2: read FIREAI_ENV directly instead of inferring it from API key presence.
// v1 used `process.env.FIREAI_API_KEY ? "production" : "development"` which is
// logically wrong — a dev machine can have an API key in .env, and a Docker
// production container sets FIREAI_ENV=production explicitly regardless of keys.
function getEnvMode(): "production" | "development" {
  const raw = (process.env.FIREAI_ENV || "development").toLowerCase();
  return raw === "production" || raw === "prod" ? "production" : "development";
}

const ENV_MODE = getEnvMode();

function findPython(): string {
  const candidates = ["python3", "python"];
  for (const cmd of candidates) {
    try {
      const result = spawnSync(cmd, ["--version"], { timeout: 3000 });
      if (result.status === 0) return cmd;
    } catch {
      continue;
    }
  }
  return "python3";
}

function getBackendDir(): string {
  // In packed asar mode, backend files are unpacked to resources/app.asar.unpacked/electron/backend
  const asarUnpacked = path.resolve(RESOURCES, "app.asar.unpacked", "electron", "backend");
  if (fs.existsSync(asarUnpacked)) {
    return asarUnpacked;
  }
  // In dev/unpacked mode, backend is at RESOURCES (project root) /backend
  return path.resolve(RESOURCES, "backend");
}

function startPythonBackend(): Promise<boolean> {
  return new Promise((resolve) => {
    if (pythonProcess) {
      resolve(true);
      return;
    }

    const python = findPython();
    const backendDir = getBackendDir();
    const appDir = path.resolve(backendDir, "..");
    const appPy = path.resolve(backendDir, "app.py");

    if (!fs.existsSync(appPy)) {
      console.error("[Python Backend] app.py not found at:", appPy);
      resolve(false);
      return;
    }

    const pathDelimiter = process.platform === "win32" ? ";" : ":";
    const env: Record<string, string> = {
      ...(process.env as Record<string, string>),
      FIREAI_ENV: ENV_MODE,
      PORT: String(PYTHON_BACKEND_PORT),
      PYTHONPATH: `${appDir}${pathDelimiter}${path.resolve(appDir, "..")}${pathDelimiter}${process.env.PYTHONPATH || ""}`,
    };

    pythonProcess = spawn(python, [appPy], {
      cwd: backendDir,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    pythonProcess.stdout?.on("data", (data: Buffer) => {
      console.log(`[Python Backend] ${data.toString().trim()}`);
    });

    pythonProcess.stderr?.on("data", (data: Buffer) => {
      console.error(`[Python Backend] ${data.toString().trim()}`);
    });

    pythonProcess.on("error", (err: Error) => {
      console.error("[Python Backend] Failed to start:", err.message);
      pythonProcess = null;
      resolve(false);
    });

    pythonProcess.on("exit", (code: number | null) => {
      console.log(`[Python Backend] Exited with code ${code}`);
      pythonProcess = null;
      resolve(false);
    });

    // Wait for backend to be healthy
    waitForBackend(30, 1000).then(resolve);
  });
}

async function waitForBackend(retries: number, delayMs: number): Promise<boolean> {
  for (let i = 0; i < retries; i++) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(`${PYTHON_BACKEND_URL}/api/health`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.ok) {
        console.log("[Python Backend] Health check passed");
        return true;
      }
    } catch {
      // Backend not ready yet
    }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  console.error("[Python Backend] Health check failed after", retries, "retries");
  return false;
}

function stopPythonBackend(): void {
  if (pythonProcess) {
    pythonProcess.kill("SIGTERM");
    setTimeout(() => {
      if (pythonProcess) {
        try { pythonProcess.kill("SIGKILL"); } catch { /* already dead */ }
      }
    }, 5000);
  }
}

function createWindow(): void {
  const isDev = process.env.ELECTRON_DEV === "true";

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: "FireAI Digital Twin",
    backgroundColor: "#0f172a",
    show: false,
    webPreferences: {
      preload: path.resolve(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  mainWindow.on("ready-to-show", () => {
    mainWindow?.show();
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    const indexPath = path.resolve(DIST, "index.html");
    mainWindow.loadFile(indexPath);
  }
}

// ── IPC: dialog option sanitization ────────────────────────────────────────
// FIX v2: the previous handlers passed `options` straight from the renderer
// into dialog.showOpenDialog / showSaveDialog. If the renderer is ever
// compromised via XSS (e.g. a malicious DWG payload that triggers an
// innerHTML sink), the attacker could request dangerous properties like
// "showHiddenFiles" or point defaultPath at sensitive system locations.
//
// These guards accept only a small, whitelisted subset of options, so even
// a fully compromised renderer cannot trick Electron into opening a file
// dialog in /etc or with hidden-files visible.

type DialogFilter = { name: string; extensions: string[] };
type SafeDialogOptions = {
  title?: string;
  defaultPath?: string;
  filters?: DialogFilter[];
  properties?: Array<"openFile" | "openDirectory" | "multiSelections">;
};

const ALLOWED_DIALOG_PROPERTIES: ReadonlySet<string> = new Set([
  "openFile",
  "openDirectory",
  "multiSelections",
]);

// Whitelist of directories that defaultPath may point into. Anything else
// (e.g. /etc, /usr, C:\Windows\System32) is rejected.
function getAllowedDefaultPathRoots(): string[] {
  const home = os.homedir();
  return [
    home,
    path.join(home, "Documents"),
    path.join(home, "Desktop"),
    path.join(home, "Downloads"),
  ];
}

function isAllowedDefaultPath(p: string): boolean {
  if (!p || typeof p !== "string") return false;
  const resolved = path.resolve(p);
  return getAllowedDefaultPathRoots().some(
    (root) => resolved === root || resolved.startsWith(root + path.sep),
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

// Phishing-y dialog titles that should be rejected (renderer social-engineering).
const DANGEROUS_TITLE_RE =
  /^(save|open|enter|confirm|update)\s+(your\s+)?(password|credentials?|token|secret|api[-_ ]?key)/i;

function sanitizeDialogOptions(raw: unknown): SafeDialogOptions {
  if (!isRecord(raw)) return {};

  const safe: SafeDialogOptions = {};

  if (typeof raw.title === "string") {
    const cleaned = raw.title.slice(0, 200).replace(/\r?\n/g, " ");
    if (!DANGEROUS_TITLE_RE.test(cleaned)) {
      safe.title = cleaned;
    } else {
      console.warn("[Electron] Rejected suspicious dialog title:", cleaned);
    }
  }

  if (typeof raw.defaultPath === "string") {
    if (isAllowedDefaultPath(raw.defaultPath)) {
      safe.defaultPath = raw.defaultPath;
    } else {
      console.warn(
        "[Electron] Rejected defaultPath outside allowed roots:",
        raw.defaultPath,
      );
    }
  }

  if (Array.isArray(raw.filters) && raw.filters.length <= 20) {
    const filters: DialogFilter[] = [];
    for (const f of raw.filters) {
      if (!isRecord(f)) continue;
      if (typeof f.name !== "string") continue;
      if (!isStringArray(f.extensions)) continue;
      filters.push({
        name: f.name.slice(0, 100),
        extensions: f.extensions.slice(0, 50).map((e) => e.toLowerCase()),
      });
      if (filters.length >= 20) break;
    }
    if (filters.length > 0) safe.filters = filters;
  }

  if (Array.isArray(raw.properties)) {
    const props: SafeDialogOptions["properties"] = [];
    for (const p of raw.properties) {
      if (typeof p === "string" && ALLOWED_DIALOG_PROPERTIES.has(p)) {
        props.push(p as "openFile" | "openDirectory" | "multiSelections");
        if (props.length >= 5) break;
      } else {
        console.warn("[Electron] Rejected dialog property:", p);
      }
    }
    if (props.length > 0) safe.properties = props;
  }

  return safe;
}

ipcMain.handle("get-app-info", () => {
  return {
    name: "FireAI Digital Twin",
    version: app.getVersion(),
    electronVersion: process.versions.electron,
    nodeVersion: process.versions.node,
    chromeVersion: process.versions.chrome,
    platform: process.platform,
    arch: process.arch,
  };
});

ipcMain.handle("get-backend-url", () => {
  return PYTHON_BACKEND_URL;
});

ipcMain.handle("show-open-dialog", async (_event: unknown, options: unknown) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  return dialog.showOpenDialog(mainWindow, sanitizeDialogOptions(options));
});

ipcMain.handle("show-save-dialog", async (_event: unknown, options: unknown) => {
  if (!mainWindow) return { canceled: true, filePath: "" };
  // Cast through unknown because the Electron namespace types are only
  // available when the `electron` package is installed (which it is in
  // the real build, just not in this offline CI sandbox).
  const safe = sanitizeDialogOptions(options);
  return dialog.showSaveDialog(
    mainWindow,
    safe as Parameters<typeof dialog.showSaveDialog>[1],
  );
});

ipcMain.handle("get-backend-status", () => {
  return { running: pythonProcess !== null, port: PYTHON_BACKEND_PORT };
});

app.whenReady().then(async () => {
  createWindow();
  const backendReady = await startPythonBackend();
  if (backendReady) {
    console.log("[App] Python backend started successfully");
  } else {
    console.warn("[App] Python backend did not start — frontend will run without API");
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("will-quit", () => {
  stopPythonBackend();
});
