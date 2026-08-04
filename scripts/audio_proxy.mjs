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

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
for (const line of fs.readFileSync(path.join(root, '.env'), 'utf8').split(/\r?\n/)) {
  if (!line || line.startsWith('#')) continue;
  const i = line.indexOf('=');
  if (i > 0) process.env[line.slice(0, i).trim()] ??= line.slice(i + 1).trim();
}

const hostAllowed = (host) => /^phonebridge\.zoho\.(in|com|eu|com\.au|jp)$/.test(host);

http.createServer(async (req, res) => {
  const requestUrl = new URL(req.url, 'http://127.0.0.1');
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
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
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
