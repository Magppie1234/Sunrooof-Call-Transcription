/**
 * Serves a built dashboard together with the /api/* routes, on one origin.
 *
 * WHY THIS EXISTS
 * `vite preview` serves dist/ and knows nothing about api/; `vercel dev` knows
 * about both but needs the CLI, a linked project and network auth. The H5 diff
 * has to run the live build end to end — the real route handlers against the
 * real database — so it needs a local origin that answers both. Forty lines of
 * stdlib does it, with no dependency and nothing to log in to.
 *
 * It emulates only what these routes actually use of Vercel's Node helpers:
 * req.query, res.status(), res.json(), res.setHeader(). If a route starts using
 * more, this is where it has to be taught about it.
 *
 *   node scripts/serve_local.mjs --dist ci-dashboard/dist --port 5200
 *
 * Not for deployment. There is no auth here; Vercel's Deployment Protection is
 * what stands in front of the real thing.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const DIST = path.resolve(ROOT, arg('dist', 'ci-dashboard/dist'));
const PORT = Number(arg('port', '5200'));

// The routes read process.env directly, as they do on Vercel. Parsed here
// rather than with dotenv: api/ takes no dependencies on purpose, and the
// point of this server is to run those routes as they actually are.
for (const line of fs.readFileSync(path.join(ROOT, '.env'), 'utf8').split(/\r?\n/)) {
  const m = /^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$/.exec(line);
  if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
}

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.woff2': 'font/woff2', '.map': 'application/json; charset=utf-8',
};

/** Resolves a request path to a route module, or null. */
function routeFor(pathname) {
  if (pathname === '/api/meta') return { file: 'api/meta.js', params: {} };
  if (pathname === '/api/calls') return { file: 'api/calls.js', params: {} };
  const m = /^\/api\/call\/([^/]+)$/.exec(pathname);
  if (m) return { file: 'api/call/[id].js', params: { id: decodeURIComponent(m[1]) } };
  return null;
}

/** The subset of Vercel's response helpers these routes use. */
function helpers(res) {
  res.status = (code) => { res.statusCode = code; return res; };
  res.json = (body) => {
    if (!res.getHeader('Content-Type')) res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(body));
    return res;
  };
  return res;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const route = routeFor(url.pathname);

  if (route) {
    helpers(res);
    req.query = { ...Object.fromEntries(url.searchParams), ...route.params };
    try {
      const mod = await import(pathToFileURL(path.join(ROOT, route.file)).href);
      await mod.default(req, res);
    } catch (err) {
      console.error(`[serve_local] ${url.pathname}`, err);
      if (!res.headersSent) res.status(500).json({ error: String(err?.message ?? err) });
    }
    return;
  }

  // Static, with an SPA fallback. The dashboard uses HashRouter, so the
  // fallback only ever catches a stray path, but a 404 on it would be a
  // confusing way to find that out.
  let file = path.join(DIST, decodeURIComponent(url.pathname));
  if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    file = path.join(DIST, 'index.html');
  }
  if (!fs.existsSync(file)) {
    res.statusCode = 404;
    res.end(`No build at ${DIST} — run the dashboard build first.`);
    return;
  }
  res.setHeader('Content-Type', TYPES[path.extname(file)] ?? 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

server.listen(PORT, () => {
  console.log(`serving ${path.relative(ROOT, DIST)} and /api/* on http://localhost:${PORT}`);
});
