const {
  app,
  BrowserWindow,
  Menu,
  dialog,
  ipcMain,
  shell,
} = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

app.setName("Chizhi SegMentor");
try {
  const userData = process.env.BOXMASK_USER_DATA
    ? path.resolve(process.env.BOXMASK_USER_DATA)
    : path.join(app.getPath("appData"), "ChizhiSegMentor");
  app.setPath("userData", userData);
} catch (error) {
  console.warn("could not relocate userData:", error.message);
}

const isPackaged = app.isPackaged;
const devShell = !isPackaged && process.env.BOXMASK_SHELL_MODE !== "prod";
const repoRoot = path.resolve(__dirname, "../..");
const dataDir = app.getPath("userData");
const runtimeDir = path.join(dataDir, "runtime");
const readyFile = path.join(runtimeDir, "ready.json");
const logDir = path.join(dataDir, "logs");
const logFile = path.join(logDir, "backend.log");

let mainWindow = null;
let backend = null;
let quitting = false;
let backendLogStream = null;

function log(...args) {
  const line = `[desktop ${new Date().toISOString()}] ${args.join(" ")}`;
  console.log(line);
  try {
    fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(path.join(logDir, "desktop.log"), `${line}\n`);
  } catch {
    // ignore logging failures
  }
}

function backendCommand() {
  if (isPackaged) {
    return {
      command: path.join(process.resourcesPath, "backend", "boxmask-backend.exe"),
      args: ["--port", "0"],
      cwd: process.resourcesPath,
    };
  }
  const python =
    process.platform === "win32"
      ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
      : path.join(repoRoot, ".venv", "bin", "python");
  return {
    command: python,
    args: ["-m", "boxmask", "--port", "0"],
    cwd: repoRoot,
  };
}

function modelPath() {
  const candidates = isPackaged
    ? [
        path.join(process.resourcesPath, "models", "boxmask_repvit_best_snapshot.pth"),
        path.join(dataDir, "models", "boxmask_repvit_best_snapshot.pth"),
      ]
    : [path.join(repoRoot, "models", "boxmask_repvit_best_snapshot.pth")];
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? candidates[0];
}

function stopBackend() {
  return new Promise((resolve) => {
    if (!backend) {
      resolve();
      return;
    }
    const child = backend;
    backend = null;
    try {
      if (process.platform === "win32" && child.pid) {
        spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
          windowsHide: true,
          stdio: "ignore",
        });
      } else {
        child.kill("SIGTERM");
      }
    } catch (error) {
      log("stopBackend failed:", error.message);
    }
    try {
      fs.rmSync(readyFile, { force: true });
    } catch {
      // ignore
    }
    const timer = setTimeout(() => resolve(), 2500);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

function startBackend() {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(runtimeDir, { recursive: true });
    fs.mkdirSync(logDir, { recursive: true });
    try {
      fs.rmSync(readyFile, { force: true });
    } catch {
      // ignore
    }

    const { command, args, cwd } = backendCommand();
    if (!fs.existsSync(command)) {
      reject(new Error(`找不到后端程序：${command}`));
      return;
    }

    backendLogStream = fs.createWriteStream(logFile, { flags: "a" });
    backend = spawn(command, args, {
      cwd,
      windowsHide: true,
      env: {
        ...process.env,
        BOXMASK_DATA_DIR: dataDir,
        BOXMASK_READY_FILE: readyFile,
        BOXMASK_LOG_FILE: logFile,
        BOXMASK_MODEL: modelPath(),
        BOXMASK_WEB_DIST: isPackaged
          ? path.join(process.resourcesPath, "web")
          : path.join(repoRoot, "apps", "web", "dist"),
        PYTHONUNBUFFERED: "1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    const writeLog = (chunk) => {
      const text = chunk.toString();
      backendLogStream?.write(text);
      if (devShell) process.stdout.write(text);
    };
    backend.stdout.on("data", writeLog);
    backend.stderr.on("data", writeLog);
    backend.once("error", (error) => reject(error));
    backend.once("exit", (code, signal) => {
      log(`backend exited code=${code} signal=${signal}`);
      backend = null;
      if (!quitting) {
        dialog.showErrorBox(
          "后端已退出",
          `推理后端意外退出（code=${code}）。请查看日志：\n${logFile}`,
        );
        app.quit();
      }
    });

    const started = Date.now();
    const poll = () => {
      if (quitting) return;
      try {
        if (fs.existsSync(readyFile)) {
          const raw = fs.readFileSync(readyFile, "utf8");
          const info = JSON.parse(raw);
          if (info && info.port && info.token) {
            resolve(info);
            return;
          }
        }
      } catch {
        // file may still be mid-write (the backend writes atomically, but be safe)
      }
      if (Date.now() - started > 120000) {
        reject(new Error(`后端启动超时。请查看日志：${logFile}`));
        return;
      }
      setTimeout(poll, 200);
    };
    poll();
  });
}

function createWindow(info) {
  const apiBase = `http://127.0.0.1:${info.port}`;
  const preload = path.join(__dirname, "preload.cjs");
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1040,
    minHeight: 720,
    show: false,
    backgroundColor: "#0f1115",
    title: "炽智 SegMentor",
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      additionalArguments: [
        `--boxmask-api=${apiBase}`,
        `--boxmask-token=${info.token}`,
      ],
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.webContents.on("did-fail-load", (_event, code, description, url) => {
    log(`did-fail-load ${code} ${description} ${url}`);
  });

  const url = devShell ? "http://127.0.0.1:5173" : `${apiBase}/`;
  mainWindow.loadURL(url);
  if (devShell && process.env.BOXMASK_DEVTOOLS === "1") {
    mainWindow.webContents.openDevTools({ mode: "detach" });
  }
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function installIpc() {
  ipcMain.handle("boxmask:selectImages", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "选择图片",
      properties: ["openFile", "multiSelections"],
      filters: [
        {
          name: "Images",
          extensions: ["jpg", "jpeg", "png", "bmp", "webp", "tif", "tiff"],
        },
      ],
    });
    return result.canceled ? [] : result.filePaths;
  });

  ipcMain.handle("boxmask:selectFolder", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "选择文件夹",
      properties: ["openDirectory"],
    });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });

  ipcMain.handle("boxmask:selectAnnotationFile", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "选择标注文件",
      properties: ["openFile"],
      filters: [
        { name: "Annotations", extensions: ["json", "xml", "csv", "txt", "yaml", "yml"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });

  ipcMain.handle("boxmask:revealFile", async (_event, filePath) => {
    if (typeof filePath === "string" && filePath) shell.showItemInFolder(filePath);
  });

  ipcMain.handle("boxmask:openLogs", async () => {
    fs.mkdirSync(logDir, { recursive: true });
    await shell.openPath(logDir);
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    installIpc();
    try {
      const info = await startBackend();
      log(`backend ready on port ${info.port}`);
      createWindow(info);
    } catch (error) {
      log("startup failed:", error.stack ?? error.message);
      dialog.showErrorBox("炽智 SegMentor 启动失败", String(error.message ?? error));
      app.quit();
    }
  });

  app.on("window-all-closed", () => {
    app.quit();
  });

  app.on("before-quit", (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    stopBackend().finally(() => app.quit());
  });
}

process.on("exit", () => {
  if (backend?.pid && process.platform === "win32") {
    try {
      spawnSync("taskkill", ["/pid", String(backend.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } catch {
      // ignore
    }
  }
});
