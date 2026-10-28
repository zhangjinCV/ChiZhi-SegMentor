/* Production-shell smoke: Electron loads FastAPI-served built assets, no Vite. */
const path = require("node:path");
const fs = require("node:fs");

delete process.env.ELECTRON_RUN_AS_NODE;

const { _electron: electron } = require("playwright");
const electronPath = require("electron");

const repo = path.resolve(__dirname, "..");

(async () => {
  fs.mkdirSync(path.join(repo, "docs"), { recursive: true });
  const app = await electron.launch({
    executablePath: electronPath,
    args: [path.join(repo, "apps", "desktop")],
    cwd: repo,
    env: { ...process.env, BOXMASK_SHELL_MODE: "prod" },
    timeout: 120000,
  });
  const page = await app.firstWindow({ timeout: 60000 });
  await page.waitForSelector(".topbar", { timeout: 30000 });
  await page.waitForSelector(".model-pill.ready", { timeout: 90000 });
  await page.waitForTimeout(600);
  const info = await page.evaluate(() => ({
    url: location.href,
    hasBridge: Boolean(window.boxmask),
    apiBase: window.boxmask?.apiBase ?? "",
    resources: performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((name) => name.includes("/assets/"))
      .length,
  }));
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-prod-empty.png") });
  console.log(JSON.stringify(info, null, 2));
  if (!info.url.startsWith("http://127.0.0.1:")) throw new Error("not served by sidecar");
  if (!info.hasBridge) throw new Error("preload bridge missing");
  if (info.resources < 1) throw new Error("built assets not loaded");
  await app.close();
  console.log("PROD UI SMOKE PASSED");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
