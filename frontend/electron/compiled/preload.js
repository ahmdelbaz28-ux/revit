import { contextBridge, ipcRenderer } from "electron";
// V262 FIX #8: Added onProtocolUrl listener for bazspark:// URLs
contextBridge.exposeInMainWorld("electronAPI", {
    getAppInfo: () => ipcRenderer.invoke("get-app-info"),
    getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),
    getBackendStatus: () => ipcRenderer.invoke("get-backend-status"),
    showOpenDialog: (options) => ipcRenderer.invoke("show-open-dialog", options),
    showSaveDialog: (options) => ipcRenderer.invoke("show-save-dialog", options),
    // V262 FIX #8: Listen for bazspark:// protocol URLs
    onProtocolUrl: (callback) => ipcRenderer.on("protocol-url", (_event, data) => callback(data)),
    // V262 FIX #5: Check for updates manually
    checkForUpdates: () => ipcRenderer.invoke("check-for-updates"),
});
