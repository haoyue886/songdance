import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = path.resolve(process.argv[2]);
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
assert.equal(manifest.production_eligible, false);
for (const [name, digest] of Object.entries(manifest.files)) {
  const target = path.resolve(root, name);
  assert.ok(target.startsWith(root + path.sep));
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex'), digest);
}
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
});
const results = { integrity: 'passed', audio: [], links: [], layouts: [], production_eligible: false };
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(pathToFileURL(path.join(root, 'index.html')).href);
  await page.waitForFunction(() => [...document.querySelectorAll('audio')].length === 3
    && [...document.querySelectorAll('audio')].every(a => a.readyState >= 1), { timeout: 15000 });
  for (let i = 0; i < 3; i++) {
    await page.locator('audio').nth(i).evaluate(async audio => {
      audio.muted = true;
      await audio.play();
    });
    await page.waitForFunction(index => document.querySelectorAll('audio')[index].currentTime > 0.1, i);
    results.audio.push(await page.locator('audio').nth(i).evaluate(audio => {
      audio.pause();
      return { source: audio.getAttribute('src'), duration: audio.duration,
        advanced: audio.currentTime > 0.1, error: audio.error?.code ?? null };
    }));
  }
  const links = await page.locator('a').evaluateAll(nodes => nodes.map(a => a.href));
  assert.equal(links.length, 6);
  for (const href of links) {
    const file = fileURLToPath(href);
    assert.ok(fs.statSync(file).size > 0);
    if (file.endsWith('.pdf')) assert.equal(fs.readFileSync(file).subarray(0, 5).toString(), '%PDF-');
    results.links.push(path.relative(root, file));
  }
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    assert.ok(fits, `horizontal overflow at ${width}`);
    results.layouts.push({ width, fits });
  }
  assert.deepEqual(errors, []);
  const target = path.join(root, 'browser-validation.json');
  fs.writeFileSync(target, JSON.stringify(results, null, 2), { flag: 'wx' });
  console.log(JSON.stringify(results));
} finally {
  await browser.close();
}
