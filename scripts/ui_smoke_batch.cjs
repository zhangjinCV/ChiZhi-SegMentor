/* Batch UI smoke: 3 real images through parse -> run -> results -> export. */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

delete process.env.ELECTRON_RUN_AS_NODE;

const { _electron: electron } = require("playwright");
const electronPath = require("electron");

const repo = path.resolve(__dirname, "..");
const packaged = process.env.BOXMASK_PACKAGED === "1";
const packagedExe = path.join(repo, "release", "win-unpacked", "ChizhiSegMentor.exe");
const shotSuffix = packaged ? "-packaged" : "";
const tank = process.env.BOXMASK_TANK_DATA || path.join(repo, "data", "tank_annotated");
const names = [
  "DJI_20250307152100_0009__000010",
  "DJI_20250307152100_0009__000035",
  "DJI_20250307152100_0009__000044",
];

(async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "segmentor-batch-ui-"));
  const images = path.join(temp, "images");
  const annotations = path.join(temp, "annotations");
  const userData = path.join(temp, "userData");
  const exportDir = path.join(temp, "export");
  fs.mkdirSync(images, { recursive: true });
  fs.mkdirSync(annotations, { recursive: true });
  fs.mkdirSync(exportDir, { recursive: true });
  for (const name of names) {
    fs.copyFileSync(path.join(tank, "JPEGImages", `${name}.jpg`), path.join(images, `${name}.jpg`));
    fs.copyFileSync(path.join(tank, "Annotations", `${name}.xml`), path.join(annotations, `${name}.xml`));
  }

  const app = await electron.launch({
    executablePath: packaged ? packagedExe : electronPath,
    args: packaged ? [] : [path.join(repo, "apps", "desktop")],
    cwd: repo,
    env: { ...process.env, BOXMASK_USER_DATA: userData },
    timeout: 180000,
  });
  const page = await app.firstWindow({ timeout: 60000 });
  await page.waitForSelector(".topbar", { timeout: 30000 });
  await page.waitForSelector(".model-pill.ready", { timeout: 90000 });
  await page.locator(".mode-tab").filter({ hasText: "批量" }).click();
  await page.waitForSelector(".batch-workspace", { timeout: 30000 });

  const cards = page.locator(".source-card");
  await cards.nth(0).locator("input").fill(images);
  await cards.nth(1).locator("input").first().fill(annotations);
  await page.getByRole("button", { name: "解析并预览" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".batch-table-row").length === 3, null, {
    timeout: 60000,
  });
  await page.screenshot({
    path: path.join(repo, "docs", `screenshot-batch-parse${shotSuffix}.png`),
  });
  console.log("parse preview ok");

  await page.getByRole("button", { name: /下一步/ }).click();
  await page.waitForSelector(".batch-param-grid", { timeout: 30000 });
  await page.getByRole("button", { name: /开始批量处理/ }).click();
  await page.waitForSelector(".batch-progress", { timeout: 30000 });
  await page.waitForFunction(
    () =>
      document.querySelector(".batch-progress-text")?.textContent === "100%" &&
      document.querySelectorAll(".batch-result-card").length === 3,
    null,
    { timeout: 180000 },
  );
  await page.waitForTimeout(700);
  await page.screenshot({
    path: path.join(repo, "docs", `screenshot-batch-result${shotSuffix}.png`),
  });
  console.log("batch run ok");

  await page.locator(".batch-result-card").first().click();
  await page.waitForSelector(".modal .batch-result-detail", { timeout: 30000 });
  await page.screenshot({
    path: path.join(repo, "docs", `screenshot-batch-detail${shotSuffix}.png`),
  });
  await page.keyboard.press("Escape");
  await page.waitForSelector(".modal", { state: "detached", timeout: 10000 });

  await page.getByRole("button", { name: "导出", exact: true }).first().click();
  await page.waitForSelector(".modal", { timeout: 10000 });
  await page.locator(".modal .path-row input").fill(exportDir);
  await page.getByLabel("LabelMe polygon JSON").check();
  await page.screenshot({
    path: path.join(repo, "docs", `screenshot-batch-export${shotSuffix}.png`),
  });
  await page.getByRole("button", { name: "开始导出" }).click();
  await page.waitForSelector(".modal", { state: "detached", timeout: 60000 });
  await page.waitForTimeout(700);

  const masks = fs.readdirSync(path.join(exportDir, "masks")).filter((name) => name.endsWith(".png"));
  const labelme = fs.readdirSync(path.join(exportDir, "labelme")).filter((name) => name.endsWith(".json"));
  const coco = JSON.parse(fs.readFileSync(path.join(exportDir, "instances.json"), "utf-8"));
  const csv = fs.readFileSync(path.join(exportDir, "results.csv"), "utf-8");
  const info = {
    masks: masks.length,
    labelme: labelme.length,
    cocoImages: coco.images.length,
    cocoAnnotations: coco.annotations.length,
    csvRows: csv.trim().split(/\r?\n/).length,
  };
  console.log(JSON.stringify(info, null, 2));
  if (info.masks !== 3 || info.labelme !== 3 || info.cocoAnnotations !== 3) {
    throw new Error("export counts mismatch");
  }
  await page.screenshot({
    path: path.join(repo, "docs", `screenshot-batch-exported${shotSuffix}.png`),
  });
  await app.close();
  fs.rmSync(temp, { recursive: true, force: true });
  console.log("BATCH UI SMOKE PASSED");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
