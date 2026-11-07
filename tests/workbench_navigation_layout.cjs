// Rendered CSS-fixture checks, not a full app or assistive-technology audit.
// Requires Playwright and its installed Chromium, or CHROMIUM_PATH pointing to
// an available Chromium executable. The runtime must permit browser processes
// and temporary files with Chromium sandboxing enabled. No server, network
// requests, or user records are used.
// Run: node tests/workbench_navigation_layout.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.join(__dirname, '..');
const nativeCSS = fs.readFileSync(path.join(root, 'desktop/design-system.css'), 'utf8');
const webCSS = fs.readFileSync(path.join(root, 'hermes_crm/static/app.css'), 'utf8');
const wordmark = fs.readFileSync(path.join(root, 'assets/brand/hermescrm-wordmark.svg'), 'utf8');
const labels = ['Overview', 'Contacts', 'Pipeline', 'Tasks', 'Activity'];
const contacts = [
  ['Casey Lane', 'VP of Growth', 'Lumen Systems', 'casey@example.com'],
  ['Avery Quinn', 'Managing Director', 'Forma Collective', 'avery@example.com'],
  ['Riley Park', 'Product Lead', 'Daybreak Digital', 'riley@example.com'],
];
function fixture(native) {
  const nav = native
    ? `<nav class="hc-tabs" aria-label="CRM sections">${labels.map(label => `<button ${label === 'Contacts' ? 'aria-current="page"' : ''}>${label}</button>`).join('')}</nav>`
    : `<nav aria-label="Main navigation">${labels.map(label => `<a href="#${label.toLowerCase()}" ${label === 'Contacts' ? 'class="active" aria-current="page"' : ''}>${label}</a>`).join('')}</nav>`;
  const rows = contacts.map(([name, role, company, email]) => `<tr><td><button class="${native ? 'hc-link-button' : 'name-button'}">${name}</button><small>${role}</small></td><td>${company}<small>${email}</small></td><td>Lead</td><td>Qualified</td></tr>`).join('');
  const table = `<table class="${native ? 'hc-table' : ''}"><thead><tr>${['Name & role', 'Company & email', 'Contact type', 'Linked deal stages'].map(name => `<th scope="col">${name}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>${native ? nativeCSS : webCSS}</style><style>html,body{margin:0;height:100%}.fixture-wordmark svg{display:block;width:180px;height:24px}td small{display:block}</style></head><body>${native
    ? `<div class="hermes-crm-native"><div class="hc-wrap"><div class="hc-brandbar"><div class="hc-brand"><span class="fixture-wordmark">${wordmark}</span><span class="hc-brand-tagline">Intelligent Relationship Management</span></div>${nav}</div><header class="hc-workspace-header"><h1>Contacts</h1></header><div class="hc-table-wrap" role="region" aria-label="Matching contacts" tabindex="0">${table}</div></div></div>`
    : `<header class="workbench-header"><a class="brand fixture-wordmark" href="#overview">${wordmark}</a>${nav}<div class="workspace-context">Profile: synthetic test</div></header><main><h1>Contacts</h1><div class="card"><div class="table-scroll" role="region" aria-label="Contacts table" tabindex="0">${table}</div></div></main>`}</body></html>`;
}
(async () => {
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true, executablePath: process.env.CHROMIUM_PATH });
  let cases = 0;
  try {
    for (const native of [true, false]) for (const colorScheme of ['light', 'dark']) for (const width of [320, 640, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme, hasTouch: width === 320 });
      const page = await context.newPage();
      await page.route('**/*', route => route.abort());
      await page.setContent(fixture(native));
      if (native && colorScheme === 'dark') await page.evaluate(() => document.documentElement.classList.add('dark'));
      const navSelector = native ? '.hc-tabs button' : 'nav a';
      const nameSelector = native ? '.hc-table .hc-link-button' : '.name-button';
      const state = await page.evaluate(({ native, navSelector, nameSelector }) => {
        const nav = document.querySelector('nav'), tab = document.querySelector(navSelector), brand = document.querySelector(native ? '.hc-brand' : '.brand');
        const name = document.querySelector(nameSelector), rows = [...document.querySelectorAll('tbody tr')];
        const style = getComputedStyle(tab), token = getComputedStyle(document.querySelector(native ? '.hermes-crm-native' : ':root'));
        return { navTop: nav.getBoundingClientRect().top, brandBottom: brand.getBoundingClientRect().bottom, fontSize: style.fontSize, tabHeight: tab.getBoundingClientRect().height,
          pageWidth: document.documentElement.scrollWidth, viewport: innerWidth, rowColors: rows.map(row => getComputedStyle(row).backgroundColor),
          nameWeight: getComputedStyle(name).fontWeight, nameColor: getComputedStyle(name).color, linkToken: token.getPropertyValue(native ? '--hc-link' : '--link').trim(),
          separator: getComputedStyle(rows[0].firstElementChild).borderBottomStyle };
      }, { native, navSelector, nameSelector });
      const label = `${native ? 'native' : 'standalone'} ${colorScheme} ${width}px`;
      assert(state.navTop >= state.brandBottom, `${label}: navigation below brand`);
      assert.equal(state.fontSize, '18px', `${label}: readable main tabs`);
      assert(state.tabHeight >= 52, `${label}: large tab targets`);
      assert(state.pageWidth <= state.viewport, `${label}: no page overflow`);
      assert.notEqual(state.rowColors[0], state.rowColors[1], `${label}: alternate row surfaces`);
      assert.equal(state.separator, 'solid', `${label}: row separators remain`);
      assert.equal(state.nameWeight, '700', `${label}: bold contact names`);
      assert.equal(state.nameColor, colorScheme === 'dark' ? 'rgb(143, 170, 255)' : 'rgb(31, 77, 255)', `${label}: blue contact names`);
      await page.locator(navSelector).last().focus();
      const tabFocus = await page.locator(navSelector).last().evaluate(el => ({ offset: getComputedStyle(el).outlineOffset, left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right, viewport: innerWidth }));
      assert.equal(tabFocus.offset, '-4px', `${label}: focus remains inside scroll region`);
      assert(tabFocus.left >= 0 && tabFocus.right <= tabFocus.viewport, `${label}: last tab scrolls into view on focus`);
      await page.locator(nameSelector).nth(1).focus();
      assert.equal(await page.locator(nameSelector).nth(1).evaluate(el => getComputedStyle(el).textDecorationLine), 'underline', `${label}: keyboard link affordance`);
      assert.notEqual(await page.locator('tbody tr').nth(1).evaluate(el => getComputedStyle(el).backgroundColor), state.rowColors[1], `${label}: focused row highlighted`);
      if (process.env.HERMES_CRM_LAYOUT_SCREENSHOTS && width === 1440) {
        await page.locator(nameSelector).nth(1).blur();
        await page.screenshot({ path: path.join(process.env.HERMES_CRM_LAYOUT_SCREENSHOTS, `${native ? 'native' : 'standalone'}-contacts-${colorScheme}.png`) });
      }
      await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
      await page.locator(navSelector).nth(1).focus();
      const forced = await page.locator(navSelector).nth(1).evaluate(el => ({ outline: getComputedStyle(el).outlineStyle, transition: getComputedStyle(el).transitionDuration }));
      assert.equal(forced.outline, 'solid', `${label}: forced-color focus visible`);
      assert.equal(forced.transition, '0s', `${label}: reduced motion respected`);
      await context.close();
      cases++;
    }
    console.log(`PASS ${cases} rendered CSS fixtures: dedicated 18px navigation, light/dark striped contacts, blue names, 320/640/1440px containment, keyboard scroll/focus, touch targets, forced colors and reduced motion`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
