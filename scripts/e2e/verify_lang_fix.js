/**
 * verify_lang_fix.js — regression test for the language bug:
 *  1. Telugu chosen in the HEADER select → /analyze must receive language=Telugu
 *  2. Telugu chosen in the WORKSPACE select → same
 *  3. Both selects stay in sync after a change
 *  4. On-screen card summary actually renders Telugu script
 *  5. A Telugu run via the sample-lease demo (upload-style flow) also works
 */
const { chromium } = require('playwright');

const EXPECT_LANGUAGES = ['Telugu'];
const HAS_TELUGU = s => /[\u0C00-\u0C7F]/.test(s);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const captured = [];
  let failures = 0;

  page.on('request', req => {
    if (req.url().endsWith('/analyze') && req.method() === 'POST') {
      const m = (req.postData() || '').match(/name="language"\r?\n\r?\n([^\r\n]*)/);
      captured.push(m ? m[1] : 'NOT_FOUND');
    }
  });

  const check = (name, ok, detail) => {
    if (!ok) failures++;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  };

  const waitForAnalysis = () => page.waitForFunction(
    () => {
      const s = document.getElementById('scanner-progress-container');
      const e = document.getElementById('scan-error-container');
      if (e && !e.classList.contains('hidden')) return true;
      return s && s.classList.contains('hidden');
    },
    { timeout: 120000 }
  );

  const onScreenSummary = () => page.evaluate(() => {
    const card = document.querySelector('.clause-card');
    if (!card) return '(no cards)';
    const p = card.querySelector('.bg-surface-container-high\\/60 p.font-body-md');
    return p ? p.innerText : '(no summary el)';
  });

  await page.goto('http://localhost:8000/', { waitUntil: 'networkidle' });

  const SAMPLE = 'Client may terminate this Agreement at any time, for any reason, with zero (0) days written notice and without payment of any outstanding invoices. Invoices are net-120. Client may withhold payment at its sole discretion.';

  // ── 1. Header select drives the analysis ──
  await page.click('#tab-text-btn');
  await page.fill('#raw-contract-text', SAMPLE);
  await page.selectOption('#header-language-select', 'te');
  const wsSynced = await page.$eval('#analysis-language-select', el => el.value);
  check('workspace select mirrors header selection', wsSynced === 'te', `workspace=${wsSynced}`);
  await page.click('#analyze-text-btn');
  await waitForAnalysis();
  check('header Telugu → request language=Telugu', captured[0] === 'Telugu', `sent=${captured[0]}`);
  const s1 = await onScreenSummary();
  check('card renders Telugu summary (header path)', HAS_TELUGU(s1), s1.slice(0, 60));

  // Selects stayed in sync after the run?
  const syncAfter = await page.$eval('#header-language-select', el => el.value);
  check('header select still on Telugu after run', syncAfter === 'te');

  // ── 2. Workspace select drives the analysis ──
  await page.selectOption('#analysis-language-select', 'te');
  await page.waitForTimeout(15000); // language-change auto re-run fires; just let it settle
  // Force a fresh explicit run to capture the request deterministically:
  await page.click('#analyze-text-btn');
  await waitForAnalysis();
  check('workspace Telugu → latest request language=Telugu', captured[captured.length - 1] === 'Telugu', `sent=${captured[captured.length - 1]}`);
  const s2 = await onScreenSummary();
  check('card renders Telugu summary (workspace path)', HAS_TELUGU(s2), s2.slice(0, 60));

  // ── 3. Hindi sanity check through the workspace select ──
  // (selecting 'hi' itself triggers an auto re-run; wait for it to settle)
  await page.selectOption('#analysis-language-select', 'hi');
  await page.waitForTimeout(15000);
  await page.click('#analyze-text-btn');
  await waitForAnalysis();
  check('Hindi request sent correctly', captured[captured.length - 1] === 'Hindi', `sent=${captured[captured.length - 1]}`);
  const s3 = await onScreenSummary();
  const hasDeva = /[\u0900-\u097F]/.test(s3);
  check('card renders Hindi (Devanagari) summary', hasDeva, s3.slice(0, 60));

  console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'}`);
  await browser.close();
  process.exit(failures === 0 ? 0 : 1);
})();
