// Screenshots docs/07-design/mockups/*.html to docs/assets/design/*.png (Playwright).
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const root = path.resolve(__dirname, '..'); const src = path.join(root, 'docs/07-design/mockups'); const out = path.join(root, 'docs/assets/design');
(async () => { fs.mkdirSync(out, { recursive: true }); const b = await chromium.launch();
  for (const f of fs.readdirSync(src).filter(f => f.endsWith('.html')).sort()) {
    const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    await p.goto('file://' + path.join(src, f)); const h = await p.evaluate(() => Math.max(900, document.documentElement.scrollHeight));
    await p.setViewportSize({ width: 1440, height: h }); await p.screenshot({ path: path.join(out, f.replace('.html', '.png')) }); await p.close(); }
  await b.close(); })();
