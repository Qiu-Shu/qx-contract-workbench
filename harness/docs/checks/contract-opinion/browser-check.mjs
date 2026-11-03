import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const require = createRequire('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json');
const { chromium } = require('playwright');
const root = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(await fs.readFile(path.join(root, 'manifest.json'), 'utf8'));
const browser = await chromium.launch({executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true,
  args: ['--disable-background-networking', '--disable-default-apps', '--no-first-run']});
const requests = [];
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1});
  page.on('request', request => requests.push(request.url()));
  await page.route(/^https?:/, route => route.abort());
  await page.goto(pathToFileURL(manifest.opinion.html_path).href);
  await page.screenshot({path: path.join(root, 'opinion-desktop.png'), fullPage: true});
  const desktop = await page.evaluate(() => ({scripts: document.scripts.length, rows: document.querySelectorAll('tbody tr').length,
    bodyWidth: document.body.scrollWidth, viewport: innerWidth, mainWidth: getComputedStyle(document.querySelector('main')).maxWidth}));
  if (desktop.scripts || desktop.rows !== 5 || desktop.bodyWidth > desktop.viewport) throw Error('Desktop layout/safety failed');
  await page.pdf({path: path.join(root, 'opinion-html-print.pdf'), format: 'A4', printBackground: true});
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: path.join(root, 'opinion-mobile.png'), fullPage: true});
  const mobile = await page.evaluate(() => ({bodyWidth: document.body.scrollWidth, viewport: innerWidth,
    tableViewport: document.querySelector('.table').clientWidth, tableContent: document.querySelector('.table').scrollWidth}));
  if (mobile.bodyWidth > mobile.viewport || mobile.tableContent <= mobile.tableViewport) throw Error('Responsive table failed');
  if (requests.some(url => /^https?:/.test(url))) throw Error('Unexpected network request');
  await fs.writeFile(path.join(root, 'browser-check.json'), JSON.stringify({desktop, mobile, requests}, null, 2));
  console.log(JSON.stringify({desktop, mobile}));
} finally { await browser.close(); }
