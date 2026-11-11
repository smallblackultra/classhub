const { app, BrowserWindow, shell, session } = require("electron");
const path = require("node:path");

const HOME_URL = "https://www.2026hfutintegratedcircuit1.com/";

function isInternal(url) {
  try {
    const host = new URL(url).hostname;
    return host === "www.2026hfutintegratedcircuit1.com"
      || host === "2026hfutintegratedcircuit1.com"
      || host.endsWith(".hfut.edu.cn");
  } catch {
    return false;
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#4b151d",
    autoHideMenuBar: true,
    title: "微电子学院班级门户",
    icon: path.join(__dirname, "build", "icon.ico"),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      spellcheck: false
    }
  });

  win.loadURL(HOME_URL);

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isInternal(url)) {
      win.loadURL(url);
    } else {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (event, url) => {
    if (!isInternal(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  return win;
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });

  createWindow();

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
