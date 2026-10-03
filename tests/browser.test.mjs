// Optional integration checks against a preinstalled Playwright + Chromium.
// No external sites, providers, crawler, or downloads are used.
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { DATASETS } from '../web/search.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const allowed = new Set(['/web/index.html', '/web/app.mjs', '/web/search.mjs', ...DATASETS.map(file => `/data/${file}`)]);
let server, browser, origin;
before(async () => {
  server = http.createServer(async (req, res) => {
    const file = new URL(req.url, 'http://localhost').pathname;
    if (!allowed.has(file)) { res.writeHead(404).end(); return; }
    try {
      const body = await readFile(new URL(`..${file}`, import.meta.url));
      res.setHeader('Content-Type', file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.mjs') ? 'text/javascript' : 'application/json');
      res.end(body);
    } catch { res.writeHead(500).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true });
});
after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); });

async function open(t, intercept) {
  const page = await browser.newPage();
  const unexpected = [];
  page.on('pageerror', error => unexpected.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { unexpected.push(`Blocked external request: ${url.origin}`); await route.abort(); return; }
    if (intercept && await intercept(route, url.pathname)) return;
    await route.continue();
  });
  t.after(async () => { await page.close(); assert.deepEqual(unexpected, []); });
  await page.goto(`${origin}/web/index.html`);
  return page;
}
async function submit(page, query) {
  await page.locator('#query').fill(query);
  await page.locator('#query').press('Enter');
}
async function ready(page) {
  await page.waitForFunction(() => document.getElementById('results').getAttribute('aria-busy') === 'false');
}

test('actual browser returns saved resources and an honest literal no-match/empty state', async t => {
  const page = await open(t);
  await submit(page, 'robotics');
  await ready(page);
  const robotics = await page.locator('.result h2').allTextContents();
  assert.ok(robotics.length > 0);
  assert.match(await page.locator('#status').textContent(), /180 unique saved titles/);
  await page.getByRole('button', { name: 'synchronization', exact: true }).click();
  await ready(page);
  const biology = await page.locator('.result h2').allTextContents();
  assert.ok(biology.includes('Synchronization of active mechanical oscillators by an inertial load'));
  assert.notDeepEqual(biology, robotics);
  const link = page.locator('.result a').first();
  assert.equal(await link.textContent(), 'Search this title on arXiv');
  assert.equal(new URL(await link.getAttribute('href')).searchParams.get('query'), biology[0]);
  assert.match(await page.locator('.result .meta').first().textContent(), /Authors:.*Summary excerpt/);
  const exactTitle = 'INTACT: Isomorphic Intent-to-Action Learning for Search-Free World Models';
  await submit(page, exactTitle); await ready(page);
  assert.equal(await page.locator('.result h2').first().textContent(), exactTitle);
  const query = '<span data-query-marker="fictional">fictionalunmatchedtopic</span>';
  await submit(page, query); await ready(page);
  assert.ok((await page.locator('#status').textContent()).includes(query));
  assert.equal(await page.locator('.result, [data-query-marker]').count(), 0);
  await submit(page, '');
  assert.match(await page.locator('#status').textContent(), /^Enter a topic/);
  assert.equal(await page.locator('.result').count(), 0);
});

test('resource title, summary and attribution render as literal text, with fixed search navigation', async t => {
  const title = '<img src=x onerror="window.fixtureExecuted=true"> Fictional Robotics';
  const summary = '<script>window.fixtureExecuted=true</script> Robotics summary.';
  const author = '<svg onload="window.fixtureExecuted=true">Author</svg>';
  const page = await open(t, async (route, file) => {
    if (!file.startsWith('/data/')) return false;
    await route.fulfill({ json: file.endsWith(DATASETS[0]) ? [{ title, summary, authors: [author], category: 'cs.RO', source: 'arxiv' }] : [] });
    return true;
  });
  await submit(page, 'robotics'); await ready(page);
  assert.equal(await page.locator('.result h2').textContent(), title);
  assert.equal(await page.locator('.result > p').first().textContent(), summary);
  assert.ok((await page.locator('.meta').textContent()).includes(author));
  assert.equal(await page.locator('#results img, #results svg, #results script').count(), 0);
  assert.equal(await page.evaluate(() => window.fixtureExecuted), undefined);
  const url = new URL(await page.locator('.result a').getAttribute('href'));
  assert.equal(url.origin, 'https://arxiv.org');
  assert.equal(url.searchParams.get('query'), title);
});

test('loading uses all four files once and only the latest submitted query wins', async t => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let loads = 0;
  const page = await open(t, async (_route, file) => {
    if (file.startsWith('/data/')) { loads++; await gate; }
    return false;
  });
  await submit(page, 'robotics');
  assert.equal(await page.locator('#results').getAttribute('aria-busy'), 'true');
  assert.match(await page.locator('#status').textContent(), /^Loading/);
  await submit(page, 'synchronization');
  release(); await ready(page);
  assert.match(await page.locator('#status').textContent(), /for “synchronization”/);
  assert.ok((await page.locator('.result h2').allTextContents()).includes('Synchronization of active mechanical oscillators by an inertial load'));
  assert.equal(loads, 4);
  await submit(page, 'robotics'); await ready(page);
  assert.equal(loads, 4);
});

for (const failure of ['http', 'json', 'schema']) {
  test(`one ${failure} failure withholds partial results and permits a complete retry`, async t => {
    let fail = true;
    const page = await open(t, async (route, file) => {
      if (fail && file.endsWith(DATASETS[3])) {
        if (failure === 'http') await route.fulfill({ status: 503, body: 'Unavailable' });
        else if (failure === 'json') await route.fulfill({ contentType: 'application/json', body: '{' });
        else await route.fulfill({ json: [{ title: 'Broken metadata' }] });
        return true;
      }
      return false;
    });
    await submit(page, 'robotics'); await ready(page);
    assert.match(await page.locator('#status').textContent(), /^Could not load all four/);
    assert.equal(await page.locator('.result').count(), 0);
    assert.equal(await page.locator('#retry').isVisible(), true);
    fail = false;
    await page.locator('#retry').click(); await ready(page);
    assert.ok(await page.locator('.result').count() > 0);
    assert.equal(await page.locator('#retry').isVisible(), false);
  });
}

test('an unfinished dataset load reaches the real ten-second deadline', { timeout: 20000 }, async t => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  t.after(() => release());
  const page = await open(t, async (route, file) => {
    if (file.endsWith(DATASETS[3])) { await gate; await route.abort().catch(() => {}); return true; }
    return false;
  });
  await submit(page, 'robotics');
  await page.waitForFunction(() => document.getElementById('retry').hidden === false, undefined, { timeout: 15000 });
  assert.match(await page.locator('#status').textContent(), /^Could not load all four/);
  assert.equal(await page.locator('.result').count(), 0);
});
