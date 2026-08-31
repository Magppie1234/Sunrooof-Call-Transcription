#!/usr/bin/env node
/**
 * Local-only proxy for Zoho PhoneBridge recordings.
 *
 * The recording service accepts the browser session cookie but rejects the
 * Python client used by batch_transcribe.py. This process stays on localhost,
 * loads the cookie from the ignored root .env file, and only forwards requests
 * to known Zoho PhoneBridge hosts.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
for (const line of fs.readFileSync(path.join(root, '.env'), 'utf8').split(/\r?\n/)) {
  if (!line || line.startsWith('#')) continue;
  const i = line.indexOf('=');
  if (i > 0) process.env[line.slice(0, i).trim()] ??= line.slice(i + 1).trim();
}

// Zoho IAM ties a session to the browser that created it, so this must match
// the User-Agent of the browser ZOHO_COOKIE was copied from. A mismatch gets
// the session invalidated server-side after a request or two -- every later
// call then 400s and the cookie looks dead when it is not.
// Override with ZOHO_UA if the cookie comes from a different browser/OS.
const UA = process.env.ZOHO_UA
  || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

const hostAllowed = (host) => /^phonebridge\.zoho\.(in|com|eu|com\.au|jp)$/.test(host);
// The interpreter differs per platform: .venv is the macOS one, .venv-win the
// Windows one, kept side by side because this tree is OneDrive-synced between
// both machines. A venv synced across leaves entries that exist but cannot
// execute -- OneDrive flattens bin/python from a symlink into a 7-byte text
// file. So probe each candidate once at startup rather than trust the path.
function resolvePython() {
  const candidates = [
    process.env.PYTHON,
    path.join(root, '.venv-win', 'Scripts', 'python.exe'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    path.join(root, '.venv', 'bin', 'python'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      if (spawnSync(candidate, ['-c', 'pass']).status === 0) return candidate;
    } catch { /* not executable on this platform -- try the next */ }
  }
  return null;
}
const PY = resolvePython();
const PY_MISSING = 'No working Python found. Looked for .venv-win/Scripts/python.exe, '
  + '.venv/Scripts/python.exe and .venv/bin/python; set PYTHON to an interpreter '
  + 'that has the project deps installed.';
if (!PY) console.warn(`Warning: ${PY_MISSING} CRM endpoints will return an error; audio playback is unaffected.`);
const SYNC_SCRIPT = path.join(root, 'scripts', 'sync_notes_to_zoho.py');

function readJsonBody(req, maxBytes = 200_000) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > maxBytes) { reject(new Error('Body too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

// Runs the sync script as a real subprocess (spawn with an argv array, never
// a shell string) — the note text a human edits in the browser can contain
// anything (quotes, backticks, semicolons), and going through a shell would
// turn that into a command-injection hole. spawn() with shell:false (the
// default) passes each argument straight to execve, so it's inert no matter
// what the string contains.
function runUpdateCrm({ callId, note, result, city }) {
  if (!PY) return Promise.reject(new Error(PY_MISSING));
  return new Promise((resolve, reject) => {
    const args = [SYNC_SCRIPT, '--call-id', String(callId)];
    if (note) args.push('--note', note);
    if (result) args.push('--result', result);
    if (city) args.push('--city', city);
    const child = spawn(PY, args, { cwd: root });
    let out = '', err = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) { reject(new Error(err.trim() || `sync script exited ${code}`)); return; }
      const line = out.trim().split('\n').pop();
      try { resolve(JSON.parse(line)); }
      catch { reject(new Error(`Could not parse sync script output: ${out.slice(0, 500)}`)); }
    });
  });
}

// Draft-only: composes the note/result/city from Supabase, never touches
// Zoho. Safe to call on every CallDetail page load.
function runDraft(callId) {
  if (!PY) return Promise.reject(new Error(PY_MISSING));
  return new Promise((resolve, reject) => {
    const child = spawn(PY, [SYNC_SCRIPT, '--draft', String(callId)], { cwd: root });
    let out = '', err = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) { reject(new Error(err.trim() || `draft script exited ${code}`)); return; }
      try { resolve(JSON.parse(out.trim().split('\n').pop())); }
      catch { reject(new Error(`Could not parse draft script output: ${out.slice(0, 500)}`)); }
    });
  });
}

http.createServer(async (req, res) => {
  const requestUrl = new URL(req.url, 'http://127.0.0.1');

  if (requestUrl.pathname === '/api/crm-draft') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    if (req.method === 'OPTIONS') { res.writeHead(204).end(); return; }
    const callId = requestUrl.searchParams.get('callId');
    if (!callId) {
      res.writeHead(400, { 'content-type': 'application/json' }).end('{"error":"Missing callId"}');
      return;
    }
    try {
      const draft = await runDraft(callId);
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify(draft));
    } catch (e) {
      res.writeHead(500, { 'content-type': 'application/json' }).end(JSON.stringify({ error: String(e.message || e) }));
    }
    return;
  }

  if (requestUrl.pathname === '/api/update-crm') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'content-type');
    if (req.method === 'OPTIONS') { res.writeHead(204).end(); return; }
    if (req.method !== 'POST') { res.writeHead(405).end(); return; }
    try {
      const body = await readJsonBody(req);
      if (!body.callId) {
        res.writeHead(400, { 'content-type': 'application/json' }).end('{"error":"Missing callId"}');
        return;
      }
      const result = await runUpdateCrm(body);
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify(result));
    } catch (e) {
      res.writeHead(500, { 'content-type': 'application/json' }).end(JSON.stringify({ error: String(e.message || e) }));
    }
    return;
  }

  if (requestUrl.pathname !== '/api/audio') {
    res.writeHead(404).end();
    return;
  }
  const targetText = requestUrl.searchParams.get('url');
  if (!targetText) {
    res.writeHead(400, { 'content-type': 'application/json' }).end('{"error":"Missing url param"}');
    return;
  }
  let target;
  try { target = new URL(targetText); } catch {
    res.writeHead(400, { 'content-type': 'application/json' }).end('{"error":"Invalid url param"}');
    return;
  }
  if (target.protocol !== 'https:' || !hostAllowed(target.hostname)) {
    res.writeHead(403, { 'content-type': 'application/json' }).end('{"error":"URL not allowed"}');
    return;
  }
  if (!process.env.ZOHO_COOKIE) {
    res.writeHead(500, { 'content-type': 'application/json' }).end('{"error":"ZOHO_COOKIE not configured"}');
    return;
  }
  try {
    const upstream = await fetch(target, {
      headers: {
        Cookie: process.env.ZOHO_COOKIE,
        'User-Agent': UA,
      },
    });
    if (!upstream.ok) {
      res.writeHead(upstream.status, { 'content-type': 'application/json' }).end(`{"error":"Upstream error: ${upstream.status}"}`);
      return;
    }
    const audio = Buffer.from(await upstream.arrayBuffer());
    res.writeHead(200, {
      'content-type': upstream.headers.get('content-type') || 'audio/mpeg',
      'content-length': String(audio.byteLength),
      'accept-ranges': 'bytes',
    }).end(audio);
  } catch {
    res.writeHead(502, { 'content-type': 'application/json' }).end('{"error":"Upstream request failed"}');
  }
}).listen(3000, '127.0.0.1', () => console.log('Audio proxy listening on http://127.0.0.1:3000'));
