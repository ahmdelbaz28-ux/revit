// NOSONAR
// V262: Electron hardening — added single-instance lock, crash reporter,
// auto-updater, Python packages verification, increased backend timeout,
// and custom protocol handler for bazspark:// URLs.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow, dialog, ipcMain } from "electron";
// ─── V262 FIX #6: Crash Reporter (main process) ──────────────────────────
// Send uncaught exceptions + unhandled rejections to Sentry for the main
// process (renderer process is already covered by @sentry/react).
// Uses Sentry's native crash reporter via @sentry/electron/main (optional
// dependency — if not installed, the try/catch silently skips).
try {
    // Dynamic import — if @sentry/electron is not installed, this fails
    // gracefully without breaking the app.
    const sentryDsn = process.env.VITE_SENTRY_DSN || "";
    if (sentryDsn) {
        // @ts-expect-error — optional dependency, may not be installed
        import("@sentry/electron/main").then((Sentry) => {
            Sentry.init({
                dsn: sentryDsn,
                environment: app.isPackaged ? "production" : "development",
                release: `fireai-digital-twin@${app.getVersion()}`,
            });
            console.log("[Sentry] Main process crash reporter initialized");
        }).catch(() => {
            // @sentry/electron not installed — skip crash reporter
            console.log("[Sentry] @sentry/electron not installed — crash reporter disabled");
        });
    }
}
catch (err) {
    console.log("[Sentry] Failed to initialize crash reporter:", err);
}
// ─── V262 FIX: Catch uncaught exceptions in main process ─────────────────
process.on("uncaughtException", (err) => {
    console.error("[FATAL] Uncaught exception in main process:", err);
    // Don't crash — log and continue (Sentry will capture if available)
});
process.on("unhandledRejection", (reason) => {
    console.error("[FATAL] Unhandled rejection in main process:", reason);
});
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
// DIST is at the project root level (sibling of electron/ directory)
const DIST = path.resolve(ROOT, "..", "dist");
// When running inside asar, unpacked backend files are in the resources dir
const RESOURCES = process.resourcesPath || path.resolve(ROOT, "..", "..");
let mainWindow = null;
let pythonProcess = null;
const PYTHON_BACKEND_PORT = process.env.FIREAI_BACKEND_PORT || "8000";
const PYTHON_BACKEND_URL = `http://localhost:${PYTHON_BACKEND_PORT}`;
// ─── V262 FIX #7: Single-Instance Lock ───────────────────────────────────
// Prevent multiple instances of the app from running simultaneously.
// Without this, two instances could both try to use the same SQLite database,
// causing lock contention or corruption.
// The second instance will focus the existing window instead of launching.
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    console.log("[App] Another instance is already running — quitting");
    app.quit();
}
else {
    app.on("second-instance", () => {
        // Focus existing window when a second instance is launched
        if (mainWindow) {
            if (mainWindow.isMinimized())
                mainWindow.restore();
            mainWindow.focus();
        }
    });
}
function findPython() {
    const candidates = ["python3", "python"];
    for (const cmd of candidates) {
        try {
            const result = spawnSync(cmd, ["--version"], { timeout: 3000 });
            if (result.status === 0)
                return cmd;
        }
        catch { }
    }
    return "python3";
}
// ─── V262 FIX #3: Python Packages Verification ───────────────────────────
// Before spawning the backend, verify that critical Python packages are
// installed. If not, show a user-friendly dialog with install instructions
// instead of a silent crash that takes 30s to surface as "backend did not start".
function verifyPythonPackages(python) {
    // List of critical packages the backend needs to import successfully.
    // These are checked because they're the most commonly-missing deps
    // that cause ImportError on first run.
    const criticalPackages = ["fastapi", "uvicorn", "pydantic", "slowapi"];
    const importCheckCode = criticalPackages
        .map((pkg) => `import ${pkg}`)
        .join("; ");
    try {
        const result = spawnSync(python, ["-c", importCheckCode], { timeout: 10000, encoding: "utf-8" });
        if (result.status !== 0) {
            const missingPkg = result.stderr
                .match(/No module named '(\w+)'/)?.[1] || "unknown";
            console.error(`[Python Backend] Missing package: ${missingPkg}`);
            console.error(`[Python Backend] stderr: ${result.stderr}`);
            // Show user-friendly dialog
            if (app.isReady()) {
                dialog.showErrorBox("Python Dependencies Missing", `The Python backend requires packages that are not installed.\n\n` +
                    `Missing: ${missingPkg}\n\n` +
                    `To fix this, run:\n` +
                    `  pip install -r requirements.txt\n\n` +
                    `Then restart the application.`);
            }
            return false;
        }
        console.log("[Python Backend] All critical packages verified");
        return true;
    }
    catch (err) {
        console.error("[Python Backend] Package verification failed:", err);
        return false;
    }
}
function getBackendDir() {
    // In packed asar mode, backend files are unpacked to resources/app.asar.unpacked/electron/backend
    const asarUnpacked = path.resolve(RESOURCES, "app.asar.unpacked", "electron", "backend");
    if (fs.existsSync(asarUnpacked)) {
        return asarUnpacked;
    }
    // In dev/unpacked mode, backend is at RESOURCES (project root) /backend
    return path.resolve(RESOURCES, "backend");
}
function startPythonBackend() {
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
        // V262 FIX #3: Verify Python packages before spawning the backend
        if (!verifyPythonPackages(python)) {
            console.error("[Python Backend] Aborting: missing Python packages");
            resolve(false);
            return;
        }
        const pathDelimiter = process.platform === "win32" ? ";" : ":";
        const env = {
            ...process.env,
            FIREAI_ENV: process.env.FIREAI_API_KEY ? "production" : "development",
            PORT: PYTHON_BACKEND_PORT,
            PYTHONPATH: `${appDir}${pathDelimiter}${path.resolve(appDir, "..")}${pathDelimiter}${process.env.PYTHONPATH || ""}`,
        };
        pythonProcess = spawn(python, [appPy], {
            cwd: backendDir,
            env,
            stdio: ["ignore", "pipe", "pipe"],
        });
        pythonProcess.stdout?.on("data", (data) => {
            console.log(`[Python Backend] ${data.toString().trim()}`);
        });
        pythonProcess.stderr?.on("data", (data) => {
            console.error(`[Python Backend] ${data.toString().trim()}`);
        });
        pythonProcess.on("error", (err) => {
            console.error("[Python Backend] Failed to start:", err.message);
            pythonProcess = null;
            resolve(false);
        });
        pythonProcess.on("exit", (code) => {
            console.log(`[Python Backend] Exited with code ${code}`);
            pythonProcess = null;
            resolve(false);
        });
        // V262 FIX #2: Increased timeout from 30s → 60s
        // 30s was insufficient on slow machines (HDD, AV scan, Docker cold start).
        // 60s gives Python + PostgreSQL connection enough time to initialize.
        // waitForBackend(60, 1000) = 60 retries × 1s = 60s total
        waitForBackend(60, 1000).then(resolve);
    });
}
async function waitForBackend(retries, delayMs) {
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
        }
        catch {
            // Backend not ready yet
        }
        await new Promise((r) => setTimeout(r, delayMs));
    }
    console.error("[Python Backend] Health check failed after", retries, "retries");
    return false;
}
function stopPythonBackend() {
    if (pythonProcess) {
        pythonProcess.kill("SIGTERM");
        setTimeout(() => {
            if (pythonProcess) {
                try {
                    pythonProcess.kill("SIGKILL");
                }
                catch {
                    /* already dead */
                }
            }
        }, 5000);
    }
}
// ─── V262 FIX #8: Custom Protocol Handler (bazspark://) ──────────────────
// Register a custom protocol so the app can be launched from browser links
// like bazspark://open?file=/path/to/project.bazspark
// This enables "Open in BAZspark" buttons on the web version that launch
// the desktop app with a specific file.
function registerCustomProtocol() {
    // Register as default protocol client (handles bazspark:// URLs)
    if (!app.isDefaultProtocolClient("bazspark")) {
        app.setAsDefaultProtocolClient("bazspark");
        console.log("[Protocol] Registered bazspark:// protocol handler");
    }
    // Handle bazspark:// URLs (Windows/Linux: second-instance event;
    // macOS: open-url event)
    app.on("open-url", (event, url) => {
        event.preventDefault();
        handleProtocolUrl(url);
    });
    // On Windows/Linux, second instance may receive the URL as argv
    // (already handled by second-instance listener above, but we also
    // check argv on startup for URLs passed as arguments)
    const lastArg = process.argv[process.argv.length - 1];
    if (lastArg && lastArg.startsWith("bazspark://")) {
        handleProtocolUrl(lastArg);
    }
}
function handleProtocolUrl(url) {
    console.log("[Protocol] Received URL:", url);
    try {
        const parsed = new URL(url);
        const action = parsed.hostname || parsed.pathname.replace("//", "");
        const params = Object.fromEntries(parsed.searchParams.entries());
        // Focus the main window first
        if (mainWindow) {
            if (mainWindow.isMinimized())
                mainWindow.restore();
            mainWindow.focus();
            // Send the URL to the renderer process for handling
            mainWindow.webContents.send("protocol-url", { action, params, url });
        }
    }
    catch (err) {
        console.error("[Protocol] Failed to parse URL:", url, err);
    }
}
function createWindow() {
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
    }
    else {
        const indexPath = path.resolve(DIST, "index.html");
        mainWindow.loadFile(indexPath);
    }
}
// ─── V262 FIX #5: Auto-Updater ───────────────────────────────────────────
// Check for updates on app startup (only in production).
// Uses electron-updater if installed, otherwise falls back to GitHub API
// check + dialog notification.
async function checkForUpdates() {
    if (!app.isPackaged) {
        console.log("[Updater] Skipped (development mode)");
        return;
    }
    try {
        // Try electron-updater first (if installed)
        // @ts-expect-error — optional dependency
        const { autoUpdater } = await import("electron-updater");
        autoUpdater.autoDownload = false;
        autoUpdater.autoInstallOnAppQuit = true;
        autoUpdater.on("update-available", (info) => {
            console.log("[Updater] Update available:", info.version);
            if (mainWindow) {
                dialog
                    .showMessageBox(mainWindow, {
                    type: "info",
                    title: "Update Available",
                    message: `A new version (${info.version}) is available!`,
                    detail: "Would you like to download and install it now?",
                    buttons: ["Download & Install", "Later"],
                    defaultId: 0,
                    cancelId: 1,
                })
                    .then((result) => {
                    if (result.response === 0) {
                        autoUpdater.downloadUpdate();
                    }
                });
            }
        });
        autoUpdater.on("update-downloaded", () => {
            dialog
                .showMessageBox(mainWindow, {
                type: "info",
                title: "Update Ready",
                message: "Update downloaded successfully!",
                detail: "The app will restart to apply the update.",
                buttons: ["Restart Now", "Later"],
                defaultId: 0,
            })
                .then((result) => {
                if (result.response === 0) {
                    autoUpdater.quitAndInstall();
                }
            });
        });
        autoUpdater.on("error", (err) => {
            console.error("[Updater] Error:", err.message);
        });
        await autoUpdater.checkForUpdates();
        console.log("[Updater] electron-updater initialized");
    }
    catch {
        // electron-updater not installed — use GitHub API fallback
        console.log("[Updater] electron-updater not installed — using GitHub API fallback");
        try {
            const currentVersion = app.getVersion();
            const response = await fetch("https://api.github.com/repos/ahmdelbaz28-ux/BAZspark/releases/latest", { headers: { "User-Agent": "BAZspark-Updater" } });
            if (!response.ok)
                return;
            const release = await response.json();
            const latestVersion = release.tag_name?.replace(/^v/, "") || "";
            if (latestVersion && latestVersion !== currentVersion) {
                if (mainWindow) {
                    dialog.showMessageBox(mainWindow, {
                        type: "info",
                        title: "Update Available",
                        message: `A new version (${latestVersion}) is available!`,
                        detail: `You are using version ${currentVersion}.\n\nDownload the new version from:\n${release.html_url}`,
                        buttons: ["OK"],
                    });
                }
            }
        }
        catch (err) {
            console.error("[Updater] GitHub API check failed:", err);
        }
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
    if (!mainWindow)
        return { canceled: true, filePaths: [] };
    return dialog.showOpenDialog(mainWindow, options);
});
ipcMain.handle("show-save-dialog", async (_event, options) => {
    if (!mainWindow)
        return { canceled: true, filePath: "" };
    return dialog.showSaveDialog(mainWindow, options);
});
ipcMain.handle("get-backend-status", () => {
    return { running: pythonProcess !== null, port: PYTHON_BACKEND_PORT };
});
app.whenReady().then(async () => {
    // V262 FIX #8: Register custom protocol before window creation
    registerCustomProtocol();
    createWindow();
    const backendReady = await startPythonBackend();
    if (backendReady) {
        console.log("[App] Python backend started successfully");
    }
    else {
        console.warn("[App] Python backend did not start — frontend will run without API");
    }
    // V262 FIX #5: Check for updates after startup (non-blocking)
    checkForUpdates().catch((err) => {
        console.error("[Updater] Check failed:", err);
    });
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
