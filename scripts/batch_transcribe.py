#!/usr/bin/env python3
"""
batch_transcribe.py  —  Download + transcribe ALL Zoho call recordings via Sarvam.

Usage:
    python scripts/batch_transcribe.py                  # all untranscribed calls >= 30s
    python scripts/batch_transcribe.py --min-duration 0 # include very short calls too
    python scripts/batch_transcribe.py --ids id1,id2    # specific calls only
    python scripts/batch_transcribe.py --batch-size 30  # files per Sarvam job (default 30)
"""
import os, sys, time, json, argparse, subprocess, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE   = Path(__file__).resolve().parent.parent
OUT    = BASE / "out"
TDIR   = OUT / "transcripts"
TDIR.mkdir(parents=True, exist_ok=True)

SARVAM_KEY  = os.getenv("SARVAM_API_KEY")
ZOHO_COOKIE = os.getenv("ZOHO_COOKIE")
REQUEST_DELAY = 3.0   # seconds between audio downloads; overridable via --delay
ZOHO_API    = os.getenv("ZOHO_API_DOMAIN", "https://www.zohoapis.in")
ZOHO_ACC    = os.getenv("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.in")
TOKEN_CACHE = BASE / ".zoho_token_cache.json"

# ── Zoho auth ──────────────────────────────────────────────────────────────
def get_token():
    try:
        cache = json.loads(TOKEN_CACHE.read_text())
        if cache.get("token") and cache.get("expiresAt", 0) > time.time()*1000 + 120_000:
            return cache["token"]
    except Exception:
        pass
    resp = requests.post(f"{ZOHO_ACC}/oauth/v2/token", data={
        "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
        "client_id":     os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "grant_type":    "refresh_token",
    }, timeout=30)
    d = resp.json()
    if not d.get("access_token"):
        print("❌ Failed to get Zoho token:", d); sys.exit(1)
    TOKEN_CACHE.write_text(json.dumps({
        "token":     d["access_token"],
        "expiresAt": int(time.time()*1000) + int(d.get("expires_in", 3600))*1000,
    }))
    return d["access_token"]

# ── Fetch ALL calls with recordings (full pagination via page_token) ───────
def fetch_calls(token, stop_after=None):
    """stop_after: stop paging once this many recording-bearing calls are
    collected. Pages arrive newest-first, so an early stop only omits OLDER
    calls — safe when the caller wants the newest N (--limit without a date
    filter). This org has 100k+ Calls; a full scan is ~10 minutes."""
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    fields  = "id,Subject,Call_Type,Who_Id,Owner,Call_Start_Time,Call_Duration,Voice_Recording__s,Call_Duration_in_seconds"
    # page_token requires the same fields/per_page/sort params on every request
    base = {"fields": fields, "per_page": 200,
            "sort_by": "Created_Time", "sort_order": "desc"}
    records, page_token, page, with_rec = [], None, 0, 0
    while True:
        params = dict(base)
        if page_token:
            params["page_token"] = page_token
        r = requests.get(f"{ZOHO_API}/crm/v7/Calls", params=params, headers=headers, timeout=60)
        if not r.ok:
            print(f"  ⚠ Calls fetch stopped at page {page+1}: HTTP {r.status_code} {r.text[:120]}")
            break
        d = r.json()
        batch = d.get("data", [])
        records.extend(batch)
        with_rec += sum(1 for c in batch if c.get("Voice_Recording__s"))
        page += 1
        if page % 10 == 0:
            print(f"    ...scanned {len(records)} call records")
        if stop_after and with_rec >= stop_after:
            print(f"    early stop: {with_rec} recorded calls within newest {len(records)}")
            break
        info = d.get("info", {})
        page_token = info.get("next_page_token")
        if not info.get("more_records") or not page_token:
            break
    return [c for c in records if c.get("Voice_Recording__s")]

# ── Audio downloads go through the local dashboard proxy ───────────────────
# The phonebridge server rejects Python's HTTP client directly (returns a
# 400 "INVALID_REQUEST" regardless of cookie/headers), but accepts the Next.js
# proxy's fetch. So we download via the dashboard's /api/audio route, which
# holds the session cookie and talks to phonebridge in a way it accepts.
# The dashboard dev server must be running (npm run dev in dashboard/).
import urllib.parse
PROXY_BASE = os.getenv("AUDIO_PROXY_BASE", "http://localhost:3000")

_dl_session = None
def get_dl_session():
    global _dl_session
    if _dl_session is None:
        _dl_session = requests.Session()
    return _dl_session

def proxy_up():
    try:
        # missing url param → 400 with a JSON error means the route is alive
        r = requests.get(f"{PROXY_BASE}/api/audio", timeout=10)
        return r.status_code in (400, 500)
    except requests.RequestException:
        return False

# ── Download one audio file (via the dashboard proxy) ──────────────────────
# Returns one of: "ok" | "no_audio" | "rate_limited" | "auth"
#   ok           – audio saved to dest
#   no_audio     – proxy returned empty body: recording purged or never captured
#   rate_limited – upstream 4xx/5xx from phonebridge: back off and retry
#   auth         – proxy reports the cookie is missing/dead
def download_audio(call_id, url, dest, retries=4):
    if dest.exists() and dest.stat().st_size > 1000:
        return "ok"   # already downloaded
    session = get_dl_session()
    proxy_url = f"{PROXY_BASE}/api/audio?url={urllib.parse.quote(url, safe='')}"
    for attempt in range(retries):
        try:
            resp = session.get(proxy_url, stream=True, timeout=120, allow_redirects=True)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1)); continue
        ct   = resp.headers.get("Content-Type", "")
        clen = resp.headers.get("Content-Length")

        # Success: real audio bytes
        if resp.status_code == 200 and "audio" in ct and clen != "0":
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(8192): f.write(chunk)
            if dest.stat().st_size >= 1000:
                return "ok"
            dest.unlink()   # empty/tiny → treat as no audio
            return "no_audio"

        # 200 but empty / no audio content → recording purged or never captured
        if resp.status_code == 200 or clen == "0":
            return "no_audio"

        # Proxy signals the cookie is unusable (500 = ZOHO_COOKIE not configured,
        # or upstream 401/403 forwarded)
        if resp.status_code in (401, 403) or (resp.status_code == 500 and "COOKIE" in resp.text.upper()):
            return "auth"

        # Anything else (upstream 4xx/5xx) → back off and retry
        if attempt < retries - 1:
            time.sleep(10 * (attempt + 1))
    return "rate_limited"

# ── Run one Sarvam batch job ──────────────────────────────────────────────
def run_sarvam_batch(mp3_files):
    from sarvamai import SarvamAI
    client = SarvamAI(api_subscription_key=SARVAM_KEY)
    job = client.speech_to_text_job.create_job(
        model="saaras:v3",
        mode="translit",        # Romanised — best for mixed Hindi/Telugu/English
        with_diarization=True,
    )
    print(f"    Sarvam job {job.job_id} — uploading {len(mp3_files)} files...")
    job.upload_files([str(p) for p in mp3_files])
    job.start()
    print("    Waiting for completion (polling every 15 s)...")
    status = job.wait_until_complete(poll_interval=15, timeout=3600)
    print(f"    Job state: {status.job_state}")
    if status.job_state.lower() != "completed":
        print("    ⚠️  Job did not complete."); return {}
    tmp = OUT / "_sarvam_tmp"
    tmp.mkdir(exist_ok=True)
    job.download_outputs(str(tmp))
    results = {}
    for jf in tmp.glob("*.json"):
        try: results[jf.name] = json.loads(jf.read_text())
        except Exception as e: print(f"    ⚠ Could not parse {jf.name}: {e}")
    return results

# ── Save transcripts ──────────────────────────────────────────────────────
def save_results(results, id_to_file):
    saved = 0
    for call_id, dest_mp3 in id_to_file.items():
        key = dest_mp3.name + ".json"
        if key not in results:
            key = next((k for k in results if dest_mp3.name in k), None)
        if not key:
            print(f"  ⚠ No transcript returned for {call_id}"); continue
        out_path = TDIR / f"{call_id}.mp3.json"
        out_path.write_text(json.dumps(results[key], ensure_ascii=False, indent=2))
        n = len(results[key].get("diarized_transcript", {}).get("entries", []))
        print(f"  ✅ {call_id} — {n} segments")
        saved += 1
    return saved

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    global REQUEST_DELAY
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids",          type=str, default="",
                        help="Comma-separated call IDs (default: all untranscribed)")
    parser.add_argument("--min-duration", type=int, default=30,
                        help="Skip calls shorter than N seconds (default 30)")
    parser.add_argument("--batch-size",   type=int, default=20,
                        help="Files per Sarvam job (max 20 enforced by API)")
    parser.add_argument("--limit",         type=int, default=0,
                        help="Cap the number of calls processed this run (0 = no cap)")
    parser.add_argument("--delay",         type=float, default=REQUEST_DELAY,
                        help=f"Seconds between audio downloads (default {REQUEST_DELAY}) — "
                             "raise it if the proxy starts throttling")
    parser.add_argument("--since",         type=str, default="",
                        help="Only calls on/after this date, YYYY-MM-DD (by Call_Start_Time)")
    parser.add_argument("--until",         type=str, default="",
                        help="Only calls on/before this date, YYYY-MM-DD (inclusive)")
    args = parser.parse_args()
    REQUEST_DELAY = args.delay

    if not SARVAM_KEY:  print("❌ Missing SARVAM_API_KEY in .env"); sys.exit(1)

    if not proxy_up():
        print(f"❌ Audio proxy not reachable at {PROXY_BASE}")
        print("   Downloads go through the local audio proxy. Start it first:")
        print("     node scripts/audio_proxy.mjs")
        print("   (or set AUDIO_PROXY_BASE if it runs elsewhere)")
        sys.exit(1)
    print(f"✅ Audio proxy up at {PROXY_BASE}")

    token = get_token()
    print("✅ Zoho token OK")

    # Newest-first early stop is only valid when nothing filters by date/id
    # and a cap is set: over-fetch 5x the cap so the duration/done filters
    # still leave enough candidates.
    stop_after = args.limit * 5 if (args.limit and not args.ids
                                    and not args.since and not args.until) else None
    all_calls = fetch_calls(token, stop_after=stop_after)
    print(f"📞 {len(all_calls)} calls with recordings found in Zoho CRM")

    # Already done
    done = {f.stem.replace(".mp3","") for f in TDIR.glob("*.json")}
    print(f"✅ Already transcribed: {len(done)}")

    def dur_secs(c):
        try: return int(c.get("Call_Duration_in_seconds") or 0)
        except: return 0

    def in_date_range(c):
        # Call_Start_Time looks like "2026-07-24T15:04:05+05:30"; the leading
        # 10 chars are the YYYY-MM-DD date, comparable as strings.
        d = (c.get("Call_Start_Time") or "")[:10]
        if not d:
            return False
        if args.since and d < args.since:
            return False
        if args.until and d > args.until:
            return False
        return True

    specific = set(filter(None, args.ids.split(",")))
    if specific:
        candidates = [c for c in all_calls if c["id"] in specific]
    else:
        # Recent-first: newest calls reliably still have audio; the oldest
        # recordings are often purged (proxy returns 204 / no content).
        # all_calls already arrives sorted by Created_Time desc.
        candidates = [c for c in all_calls
                      if c["id"] not in done and dur_secs(c) >= args.min_duration
                      and (not (args.since or args.until) or in_date_range(c))]

    if args.since or args.until:
        print(f"📅 Date filter: {args.since or 'start'} → {args.until or 'now'}")

    if not candidates:
        print("🎉 Nothing left to transcribe!"); return

    if args.limit and len(candidates) > args.limit:
        candidates = candidates[:args.limit]
        print(f"🔒 Capping this run at {args.limit} calls (--limit)")

    total_secs = sum(dur_secs(c) for c in candidates)
    print(f"\n📋 {len(candidates)} calls to transcribe "
          f"(~{total_secs//60} min total audio)\n")

    # ── Process in batches: download → transcribe → save (incremental) ─────
    # Interleaving keeps progress durable — a mid-run cookie expiry only loses
    # the current batch, and everything already saved stays on disk.
    call_batches = [candidates[i:i+args.batch_size]
                    for i in range(0, len(candidates), args.batch_size)]
    print(f"🎙  {len(call_batches)} batch(es) of up to {args.batch_size} files each\n")

    total_saved = no_audio_count = rate_limit_hits = 0
    for b_num, call_batch in enumerate(call_batches, 1):
        print(f"── Batch {b_num}/{len(call_batches)} ({len(call_batch)} calls) ──")
        mp3_ready, id_to_file = [], {}
        for c in call_batch:
            name  = (c.get("Who_Id") or {}).get("name", "Unknown")
            agent = (c.get("Owner")  or {}).get("name", "Unknown")
            dest  = OUT / f"{c['id']}.mp3"
            status = download_audio(c["id"], c["Voice_Recording__s"], dest)

            if status == "ok":
                print(f"  ⬇  {agent} → {name} ({dur_secs(c)}s)")
                mp3_ready.append(dest); id_to_file[c["id"]] = dest
                rate_limit_hits = 0
            elif status == "no_audio":
                no_audio_count += 1        # recording purged — nothing to do
            elif status == "auth":
                print("\n⛔ Proxy returned a login/auth response — the ZOHO_COOKIE is dead.")
                print("   Refresh ZOHO_COOKIE in .env and re-run; saved transcripts are kept.")
                print(f"\n{'='*50}\n✅ Saved {total_saved} new transcripts before stopping.")
                return
            elif status == "rate_limited":
                rate_limit_hits += 1
                print(f"  ⏳ Proxy throttling (hit {rate_limit_hits}) — pausing 60s")
                time.sleep(60)
                if rate_limit_hits >= 5:
                    print("\n⛔ Sustained throttling from the Zoho proxy — backing off.")
                    print("   Wait a while, then re-run; saved transcripts are kept and skipped.")
                    print(f"\n{'='*50}\n✅ Saved {total_saved} new transcripts before stopping.")
                    return

            time.sleep(REQUEST_DELAY)   # pace requests to stay under the proxy limit

        if not mp3_ready:
            print(f"  ⚠ Nothing downloaded this batch "
                  f"({no_audio_count} with no audio so far), skipping.\n"); continue

        # A transient network error (DNS blip, dropped connection) while polling
        # Sarvam must not kill the whole run — log it and move on. These calls
        # aren't saved, so they stay candidates and get retried on the next run.
        try:
            results = run_sarvam_batch(mp3_ready)
        except Exception as e:
            print(f"  ⚠ Batch {b_num} failed ({type(e).__name__}: {e}) — "
                  f"skipping, will retry on re-run\n")
            time.sleep(10)
            continue
        if results:
            saved = save_results(results, id_to_file)
            total_saved += saved
            print(f"  💾 Saved {saved} transcripts (running total: {total_saved})\n")
        else:
            print("  ⚠ No results for this batch\n")

    # Sarvam mishears "Sunrooof" many ways (Sunroof, Sun Roof, Sunruf, ...).
    # Normalise automatically so no transcript is ever left with a wrong company
    # name; it's free, deterministic, and safe to re-run.
    if total_saved:
        print("\n🔤 Normalising company-name mishears...")
        try:
            subprocess.run([sys.executable, str(BASE / "scripts" / "clean_names.py"),
                            "--local-only"], check=True)
        except Exception as e:
            print(f"  ⚠ name cleanup failed ({e}) — run scripts/clean_names.py manually")

    print(f"\n{'='*50}")
    print(f"✅ Done! {total_saved} new transcripts saved.")
    if no_audio_count:
        print(f"   ({no_audio_count} calls had no downloadable audio — purged/empty recordings)")
    print("   Rebuild ci-dashboard/src/data/real/dataset.json to publish them.")

if __name__ == "__main__":
    main()
