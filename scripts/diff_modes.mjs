/**
 * H5: renders every page in both data modes and diffs what they display.
 *
 * WHAT IT COMPARES, AND WHY IT IS THE RENDERED TEXT
 * Not a list of KPIs someone remembered to enumerate — the whole rendered text
 * of each page, every number and label the user can actually see. A hand-kept
 * KPI list checks the metrics you thought of; this checks the ones you did not,
 * which is where a snapshot-to-database migration goes wrong. The two modes run
 * the SAME applyFilters() and the SAME metrics.ts over records that should be
 * byte-identical, so the correct result is an empty diff, and anything at all
 * in the output is a finding.
 *
 * It drives a real headless Chrome against a real build served by
 * scripts/serve_local.mjs, so the live side exercises the actual route handlers
 * against the actual database. Nothing here is stubbed.
 *
 *   node scripts/diff_modes.mjs
 *   node scripts/diff_modes.mjs --routes /,/voice --keep
 *
 * Expects both builds to exist already:
 *   VITE_DATA_MODE=real npx vite build --outDir dist-real
 *   VITE_DATA_MODE=live npx vite build --outDir dist-live
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const has = (name) => process.argv.includes(`--${name}`);

const ROUTES = arg('routes', [
  '/', '/voice', '/faqs', '/regions', '/sales', '/agents', '/actions',
  '/calls', '/alerts', '/data', '/advanced-qa', '/review-sets',
  // A call detail page: the one route whose data comes from a per-call fetch
  // (a static file in real mode, GET /api/call/[id] in live) rather than from
  // the list payload, so it is the only place the two paths could diverge on
  // something the list diff would never see.
  '/calls/887064000041661165',
].join(',')).split(',');

const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium',
].find((p) => fs.existsSync(p));
if (!CHROME) {
  console.error('No headless browser found. Install Chrome or Edge.');
  process.exit(2);
}

const MODES = [
  { name: 'real', dist: 'ci-dashboard/dist-real', port: 5210 },
  { name: 'live', dist: 'ci-dashboard/dist-live', port: 5211 },
];

const work = fs.mkdtempSync(path.join(os.tmpdir(), 'diff-modes-'));

function serve({ dist, port }) {
  const child = spawn(process.execPath,
    [path.join(ROOT, 'scripts/serve_local.mjs'), '--dist', dist, '--port', String(port)],
    { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stderr.on('data', (d) => process.stderr.write(`[serve ${port}] ${d}`));
  return child;
}

async function waitFor(port) {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://localhost:${port}/`);
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`server on ${port} never came up`);
}

/**
 * Renders one route and returns its visible text.
 *
 * --virtual-time-budget lets the page's own timers and fetches run to
 * completion before the DOM is dumped: the live build has to page 6,253 calls
 * out of the API first, and a fixed sleep would either be wasteful or race it.
 */
function render(port, route, profile) {
  return new Promise((resolve, reject) => {
    const out = [];
    const child = spawn(CHROME, [
      '--headless=old', '--disable-gpu', '--no-sandbox', '--no-first-run',
      '--virtual-time-budget=120000', `--user-data-dir=${profile}`,
      '--dump-dom', `http://localhost:${port}/#${route}`,
    ], { stdio: ['ignore', 'pipe', 'ignore'] });
    child.stdout.on('data', (d) => out.push(d));
    child.on('error', reject);
    child.on('close', () => resolve(Buffer.concat(out).toString('utf8')));
  });
}

/**
 * Visible text, one node per line.
 *
 * Scripts and styles are stripped first — the live build's chunk hashes differ
 * from the real build's, and a diff that reported that on every page would bury
 * the one line that matters.
 */
function visibleText(html) {
  const body = html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '');
  return body
    .replace(/<[^>]+>/g, '\n')
    .split('\n')
    .map((l) => l.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim())
    .filter(Boolean);
}

/**
 * Differences that are correct rather than tolerated.
 *
 * An allowlist, not a normaliser: each entry has to say WHY the two sides
 * differ, and it matches only the specific pair it describes. Rewriting either
 * side to make the diff pretty would hide the next real difference in the same
 * place, which is the whole reason for comparing rendered output.
 */
const EXPECTED = [
  {
    route: '/data',
    why: 'Audit-log seed line. Each service states its own provenance, which is the '
       + 'point of the line: the snapshot names the pipeline that built it, the live '
       + 'service names the database and the snapshot stamp it read. Not a metric.',
    match: (real, live) =>
      real.startsWith('Dataset built from Zoho CRM') && live.startsWith('Loaded from Supabase:'),
  },
];

function classify(route, d) {
  const accepted = [];
  const unexplained = [];
  for (const x of d) {
    const rule = EXPECTED.find((e) => e.route === route && e.match(x.real, x.live));
    (rule ? accepted : unexplained).push({ ...x, why: rule?.why });
  }
  return { accepted, unexplained };
}

function diff(a, b) {
  const out = [];
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) out.push({ line: i, real: a[i] ?? '(absent)', live: b[i] ?? '(absent)' });
  }
  return out;
}

const servers = [];
try {
  for (const m of MODES) {
    if (!fs.existsSync(path.join(ROOT, m.dist))) {
      console.error(`Missing build: ${m.dist}. Build both modes first (see the header of this file).`);
      process.exit(2);
    }
    servers.push(serve(m));
  }
  await Promise.all(MODES.map((m) => waitFor(m.port)));

  let totalDiffs = 0;
  let totalAccepted = 0;
  const summary = [];

  for (const route of ROUTES) {
    const [realHtml, liveHtml] = await Promise.all(MODES.map((m, i) =>
      render(m.port, route, path.join(work, `profile-${i}`))));
    const real = visibleText(realHtml);
    const live = visibleText(liveHtml);
    const { accepted, unexplained } = classify(route, diff(real, live));
    totalDiffs += unexplained.length;
    totalAccepted += accepted.length;
    summary.push({ route, lines: real.length, diffs: unexplained.length });

    const label = `${route.padEnd(34)} ${String(real.length).padStart(5)} text nodes`;
    if (unexplained.length === 0) {
      console.log(`ok   ${label}  identical${accepted.length ? ` (${accepted.length} accepted)` : ''}`);
    } else {
      console.log(`DIFF ${label}  ${unexplained.length} unexplained line(s)`);
      for (const x of unexplained.slice(0, 12)) {
        console.log(`       line ${x.line}`);
        console.log(`         real: ${x.real.slice(0, 160)}`);
        console.log(`         live: ${x.live.slice(0, 160)}`);
      }
      if (unexplained.length > 12) console.log(`       … ${unexplained.length - 12} more`);
    }
    for (const x of accepted) {
      console.log(`     accepted difference, ${route} line ${x.line}: ${x.why}`);
      console.log(`         real: ${x.real.slice(0, 120)}`);
      console.log(`         live: ${x.live.slice(0, 120)}`);
    }
    if (has('keep')) {
      fs.writeFileSync(path.join(work, `${route.replace(/\W+/g, '_') || 'root'}.real.txt`), real.join('\n'));
      fs.writeFileSync(path.join(work, `${route.replace(/\W+/g, '_') || 'root'}.live.txt`), live.join('\n'));
    }
  }

  const rendered = summary.reduce((a, s) => a + s.lines, 0);
  console.log(`\n${ROUTES.length} routes, ${rendered.toLocaleString()} rendered text nodes compared`);
  if (totalAccepted) console.log(`${totalAccepted} accepted difference(s), each justified above`);
  console.log(totalDiffs === 0
    ? 'MODE DIFF: EMPTY — real and live display the same numbers on every page'
    : `MODE DIFF: ${totalDiffs} UNEXPLAINED LINE(S) — live is not a drop-in replacement yet`);
  if (has('keep')) console.log(`captures kept in ${work}`);
  process.exitCode = totalDiffs === 0 ? 0 : 1;
} finally {
  for (const s of servers) s.kill();
  if (!has('keep')) fs.rmSync(work, { recursive: true, force: true });
}
