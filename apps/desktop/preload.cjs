const { contextBridge, ipcRenderer, webUtils } = require("electron");

function argValue(prefix) {
  const entry = process.argv.find((value) => value.startsWith(prefix));
  return entry ? entry.slice(prefix.length) : "";
}

const apiBase = argValue("--boxmask-api=");
const token = argValue("--boxmask-token=");

contextBridge.exposeInMainWorld("boxmask", {
  apiBase,
  token,
  platform: process.platform,
  selectImages: () => ipcRenderer.invoke("boxmask:selectImages"),
  selectFolder: () => ipcRenderer.invoke("boxmask:selectFolder"),
  selectAnnotationFile: () => ipcRenderer.invoke("boxmask:selectAnnotationFile"),
  getPathForFile: (file) => {
    try {
      return webUtils.getPathForFile(file);
    } catch {
      return "";
    }
  },
  revealFile: (filePath) => ipcRenderer.invoke("boxmask:revealFile", filePath),
  openLogs: () => ipcRenderer.invoke("boxmask:openLogs"),
});
