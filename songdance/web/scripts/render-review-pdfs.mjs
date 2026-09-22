import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "@playwright/test";

const root = path.resolve(process.argv[2]);
const files = fs.readdirSync(root, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => path.join(root, entry.name, "score.musicxml"))
  .filter((file) => fs.existsSync(file));
const defaultChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.PLAYWRIGHT_CHROME_PATH || (fs.existsSync(defaultChrome) ? defaultChrome : undefined);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.setContent('<main id="score"></main>');
await page.addScriptTag({ path: path.resolve("node_modules/opensheetmusicdisplay/build/opensheetmusicdisplay.min.js") });
try {
  for (const file of files) {
    const xml = fs.readFileSync(file, "utf8");
    await page.evaluate(async (source) => {
      const container = document.querySelector("#score");
      container.replaceChildren();
      const osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(container, { backend: "svg", autoResize: false, drawTitle: true });
      await osmd.load(source);
      osmd.render();
    }, xml);
    await page.pdf({ path: path.join(path.dirname(file), "score.pdf"), format: "A4", printBackground: true, margin: { top: "12mm", right: "10mm", bottom: "12mm", left: "10mm" } });
  }
} finally {
  await browser.close();
}
