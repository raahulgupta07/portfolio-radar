// Time the main pages in a real browser against a gateway on the load-test database.
//   node scripts/loadtest-pages.mjs http://127.0.0.1:5174
// Needs Playwright (the web app's dev dependency) and DEV_LOGIN=true on that web server.
import { chromium } from '@playwright/test';

const base = process.argv[2] ?? 'http://127.0.0.1:5174';
const pages = ['/', '/projects', '/roadmap', '/risks', '/radar'];
const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`${base}/login`);
await page.click('button[value="dev-viewer"]');
await page.waitForLoadState('networkidle');
const out = {};
for (const path of pages) {
	const runs = [];
	for (let i = 0; i < 4; i++) {
		const t = Date.now();
		const resp = await page.goto(base + path, { waitUntil: 'load' });
		const loaded = Date.now() - t;
		const html = (await resp.body()).length;
		const nav = await page.evaluate(() => {
			const n = performance.getEntriesByType('navigation')[0];
			return { ttfb: Math.round(n.responseStart), dom: Math.round(n.domContentLoadedEventEnd) };
		});
		runs.push({ loaded, html, ...nav });
	}
	const cold = runs[0];
	const warm = runs.slice(1).sort((a, b) => a.loaded - b.loaded)[1];
	out[path] = { cold_ms: cold.loaded, warm_ms: warm.loaded, ttfb_ms: warm.ttfb, html_kb: Math.round(warm.html / 1024) };
}
console.log(JSON.stringify(out, null, 2));
await browser.close();
