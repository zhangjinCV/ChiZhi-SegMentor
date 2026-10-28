/* Full production test: packaged exe, FastAPI-served assets, synthetic drag/drop. */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

delete process.env.ELECTRON_RUN_AS_NODE;

const { _electron: electron } = require("playwright");

const repo = path.resolve(__dirname, "..");
const exe = path.join(repo, "release", "win-unpacked", "ChizhiSegMentor.exe");
const imagePath =
  process.env.BOXMASK_SMOKE_IMAGE ||
  path.join(repo, "data", "tank_annotated", "JPEGImages", "DJI_20250307152100_0009__000010.jpg");

(async () => {
  if (!fs.existsSync(exe)) throw new Error(`packaged app not found: ${exe}`);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "segmentor-packaged-"));
  const userData = path.join(temp, "userData");
  const app = await electron.launch({
    executablePath: exe,
    args: [],
    env: { ...process.env, BOXMASK_USER_DATA: userData },
    timeout: 180000,
  });
  const page = await app.firstWindow({ timeout: 60000 });
  await page.waitForSelector(".topbar", { timeout: 30000 });
  await page.waitForSelector(".model-pill.ready", { timeout: 120000 });
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-packaged-empty.png") });
  console.log("packaged shell/model ready");

  const b64 = fs.readFileSync(imagePath).toString("base64");
  await page.evaluate(
    ({ data, name }) => {
      const bytes = Uint8Array.from(atob(data), (char) => char.charCodeAt(0));
      const file = new File([bytes], name, { type: "image/jpeg" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      const event = new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer: transfer,
      });
      document.querySelector(".app-shell")?.dispatchEvent(event);
    },
    { data: b64, name: path.basename(imagePath) },
  );
  await page.waitForSelector(".image-item", { timeout: 60000 });
  await page.waitForSelector("canvas", { timeout: 60000 });
  await page.waitForTimeout(600);

  const pane = await page.locator(".canvas-pane").boundingBox();
  if (!pane) throw new Error("canvas pane not found");
  const scale = Math.min((pane.width - 108) / 1920, (pane.height - 108) / 1080);
  const ox = pane.x + (pane.width - 1920 * scale) / 2;
  const oy = pane.y + (pane.height - 1080 * scale) / 2;
  await page.mouse.move(ox + 503 * scale, oy + 1 * scale);
  await page.mouse.down();
  await page.mouse.move(ox + 1676 * scale, oy + 604 * scale, { steps: 12 });
  await page.mouse.up();
  await page.waitForSelector(".mask-preview img", { timeout: 120000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-packaged-result.png") });

  const info = await page.evaluate(() => ({
    url: location.href,
    boxes: document.querySelectorAll(".box-row").length,
    hasMask: Boolean(document.querySelector(".mask-preview img")),
    stats: Array.from(document.querySelectorAll(".stat .v")).map((el) => el.textContent),
  }));
  console.log(JSON.stringify(info, null, 2));
  if (!info.url.startsWith("http://127.0.0.1:")) throw new Error("not served by packaged sidecar");
  if (!info.hasMask) throw new Error("mask missing");
  await app.close();
  fs.rmSync(temp, { recursive: true, force: true });
  console.log("PACKAGED UI SMOKE PASSED");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
