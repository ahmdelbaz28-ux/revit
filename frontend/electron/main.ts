import fs from "node:fs";
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

const PYTHON_BACKEND_PORT = process.env.FIREAI_BACKEND_PORT || "8000";
const PYTHON_BACKEND_URL = `http://localhost:${PYTHON_BACKEND_PORT}`;

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

    const env: Record<string, string> = {
      ...(process.env as Record<string, string>),
      FIREAI_ENV: "production",
      PORT: PYTHON_BACKEND_PORT,
      PYTHONPATH: `${appDir}${path.delimiter}${path.resolve(appDir, "..")}${path.delimiter}${process.env.PYTHONPATH || ""}`,
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

ipcMain.handle("show-open-dialog", async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  return dialog.showOpenDialog(mainWindow, options);
});

ipcMain.handle("show-save-dialog", async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePath: "" };
  return dialog.showSaveDialog(mainWindow, options);
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
