import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  getAppInfo: () => ipcRenderer.invoke("get-app-info"),
  getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),
  getBackendStatus: () => ipcRenderer.invoke("get-backend-status"),
  showOpenDialog: (options: any) => ipcRenderer.invoke("show-open-dialog", options),
  showSaveDialog: (options: any) => ipcRenderer.invoke("show-save-dialog", options),
});
