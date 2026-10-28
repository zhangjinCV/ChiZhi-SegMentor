/* Launch the real Electron app, import a sample image, add a box, and screenshot. */
const path = require("node:path");
const fs = require("node:fs");

// This shell may export ELECTRON_RUN_AS_NODE=1 globally; Playwright's Electron
// driver must launch the real Electron binary, not Node.
delete process.env.ELECTRON_RUN_AS_NODE;

const { _electron: electron } = require("playwright");

const repo = path.resolve(__dirname, "..");
const imagePath =
  process.env.BOXMASK_SMOKE_IMAGE ||
  path.join(repo, "data", "tank_annotated", "JPEGImages", "DJI_20250307152100_0009__000010.jpg");
const electronPath = require("electron");

(async () => {
  fs.mkdirSync(path.join(repo, "docs"), { recursive: true });
  const app = await electron.launch({
    executablePath: electronPath,
    args: [path.join(repo, "apps", "desktop")],
    cwd: repo,
    env: { ...process.env },
    timeout: 120000,
  });

  const page = await app.firstWindow({ timeout: 60000 });
  await page.waitForSelector(".topbar", { timeout: 30000 });
  await page.evaluate(() => window.localStorage.clear());
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector(".topbar", { timeout: 30000 });
  await page.waitForSelector(".model-pill.ready", { timeout: 90000 });
  console.log("model ready");
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-empty.png") });

  await page.evaluate((p) => window.__boxmaskImportPaths([p]), imagePath);
  await page.waitForSelector(".image-item", { timeout: 30000 });
  await page.waitForSelector("canvas", { timeout: 30000 });
  await page.waitForTimeout(600);
  console.log("image loaded");
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-image.png") });

  // Draw a real box with the mouse (the initial tool is "draw").
  const pane = await page.locator(".canvas-pane").boundingBox();
  if (!pane) throw new Error("canvas pane not found");
  const scale = Math.min((pane.width - 108) / 1920, (pane.height - 108) / 1080);
  const ox = pane.x + (pane.width - 1920 * scale) / 2;
  const oy = pane.y + (pane.height - 1080 * scale) / 2;
  const p1 = { x: ox + 503 * scale, y: oy + 1 * scale };
  const p2 = { x: ox + 1676 * scale, y: oy + 604 * scale };
  await page.mouse.move(p1.x, p1.y);
  await page.mouse.down();
  await page.mouse.move(p2.x, p2.y, { steps: 12 });
  await page.mouse.up();
  await page.waitForSelector(".box-row", { timeout: 30000 });
  await page.waitForSelector(".mask-preview img", { timeout: 90000 });
  await page.waitForTimeout(4200);
  console.log("mask ready (mouse-drawn box)");
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-result.png") });

  await page.locator('button[title="撤销 (Ctrl+Z)"]').click();
  await page.waitForFunction(() => document.querySelectorAll(".box-row").length === 0);
  await page.locator('button[title="重做 (Ctrl+Y)"]').click();
  await page.waitForSelector(".box-row", { timeout: 30000 });
  await page.getByRole("button", { name: "重新分割" }).click();
  await page.waitForSelector(".mask-preview img", { timeout: 90000 });
  console.log("undo/redo ok");

  await page.getByRole("button", { name: "输入预览" }).click();
  await page.waitForSelector(".modal .preview-card img", { timeout: 60000 });
  await page.waitForTimeout(500);
  const previews = await page.locator(".modal .preview-card img").count();
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-preview.png") });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);

  // Reload: session persistence should restore image + box (but not the mask),
  // then the user can rerun the selected box.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector(".image-item", { timeout: 30000 });
  await page.waitForSelector("canvas", { timeout: 30000 });
  await page.waitForSelector(".box-row", { timeout: 30000 });
  await page.waitForTimeout(500);
  const restoredMaskBefore = await page.locator(".mask-preview img").count();
  await page.getByRole("button", { name: "重新分割" }).click();
  await page.waitForSelector(".mask-preview img", { timeout: 90000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(repo, "docs", "screenshot-restored.png") });

  const info = await page.evaluate(() => ({
    status: document.querySelector(".statusbar")?.innerText ?? "",
    boxes: document.querySelectorAll(".box-row").length,
    coords: document.querySelector(".box-coords")?.textContent ?? "",
    hasPreview: Boolean(document.querySelector(".mask-preview img")),
    stats: Array.from(document.querySelectorAll(".stat .v")).map((el) => el.textContent),
  }));
  console.log(
    JSON.stringify({ ...info, previewImages: previews, restoredMaskBefore }, null, 2),
  );
  await app.close();
  console.log("UI SMOKE PASSED");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
