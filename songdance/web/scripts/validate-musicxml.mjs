import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "@playwright/test";

const files = process.argv.slice(2).map((value) => path.resolve(value));
if (files.length === 0) {
  throw new Error("at least one MusicXML path is required");
}

const defaultChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const configuredChrome = process.env.PLAYWRIGHT_CHROME_PATH;
const executablePath = configuredChrome || (fs.existsSync(defaultChrome) ? defaultChrome : undefined);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.setContent('<main id="score"></main>');
await page.addScriptTag({
  path: path.resolve("node_modules/opensheetmusicdisplay/build/opensheetmusicdisplay.min.js"),
});

const results = {};
try {
  for (const file of files) {
    const xml = fs.readFileSync(file, "utf8");
    results[file] = await page.evaluate(async (source) => {
      const container = document.querySelector("#score");
      container.replaceChildren();
      const osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(container, {
        backend: "svg",
        autoResize: false,
        drawTitle: false,
      });
      await osmd.load(source);
      osmd.render();
      return {
        status: "passed",
        measure_count: osmd.Sheet.SourceMeasures.length,
        svg_count: container.querySelectorAll("svg").length,
      };
    }, xml);
  }
} finally {
  await browser.close();
}

process.stdout.write(`${JSON.stringify(results)}\n`);
