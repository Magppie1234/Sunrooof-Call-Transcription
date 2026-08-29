#!/usr/bin/env python3
"""Transcribe Sameer's training voice notes with Sarvam.

Separate from batch_transcribe.py for one reason that matters: that module
downloads Sarvam output into a shared out/_sarvam_tmp/ which is never cleared,
then globs the whole directory — so a job's results come back mixed with every
previous run's leftovers. It gets away with it because save_results() looks up
results by filename, but anything that iterates the returned dict sees stale
data. This uses a fresh temp directory per batch instead.

Usage:
    .venv/bin/python scripts/transcribe_voice_notes.py                # all
    .venv/bin/python scripts/transcribe_voice_notes.py --limit 5      # sample
    .venv/bin/python scripts/transcribe_voice_notes.py --pattern "*.opus"
"""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent.parent
OUTDIR = BASE / "out" / "voice_notes"
SARVAM_KEY = os.getenv("SARVAM_API_KEY")


def run_batch(files):
    """Transcribe one batch; returns {filename: result}. Fresh temp dir."""
    from sarvamai import SarvamAI
    client = SarvamAI(api_subscription_key=SARVAM_KEY)
    job = client.speech_to_text_job.create_job(
        model="saaras:v3",
        mode="translit",          # romanised Hindi/English, same as the call pipeline
        with_diarization=True,
    )
    print(f"    job {job.job_id} — uploading {len(files)} file(s)…", flush=True)
    job.upload_files([str(p) for p in files])
    job.start()
    status = job.wait_until_complete(poll_interval=15, timeout=3600)
    if status.job_state.lower() != "completed":
        print(f"    ⚠ job state {status.job_state}")
        return {}
    tmp = Path(tempfile.mkdtemp(prefix="sarvam_vn_"))
    try:
        job.download_outputs(str(tmp))
        out = {}
        for jf in sorted(tmp.glob("*.json")):
            try:
                out[jf.name] = json.loads(jf.read_text())
            except ValueError as e:
                print(f"    ⚠ could not parse {jf.name}: {e}")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def plain_text(result):
    """Prefer the diarized turns; fall back to the flat transcript."""
    entries = (result.get("diarized_transcript") or {}).get("entries") or []
    if entries:
        return "\n".join(
            f"[{int(e.get('start_time_seconds', 0)) // 60}:"
            f"{int(e.get('start_time_seconds', 0)) % 60:02d}] "
            f"S{e.get('speaker_id')}: {(e.get('transcript') or '').strip()}"
            for e in entries if (e.get("transcript") or "").strip())
    return result.get("transcript") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path.home() / "Downloads"))
    ap.add_argument("--pattern", default="WhatsApp Audio 2026-08-13*.opus")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch-size", type=int, default=20)
    args = ap.parse_args()

    if not SARVAM_KEY:
        raise SystemExit("❌ SARVAM_API_KEY missing from .env")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.dir).expanduser().glob(args.pattern))
    done = {p.stem for p in OUTDIR.glob("*.json")}
    pending = [f for f in files if f.stem not in done]
    if args.limit:
        pending = pending[:args.limit]

    print(f"📂 {len(files)} file(s) matched, {len(files) - len(pending)} already done, "
          f"{len(pending)} to transcribe")
    if not pending:
        print("🎉 nothing to do")
        return

    size = min(max(args.batch_size, 1), 20)   # Sarvam caps a job at 20 files
    batches = [pending[i:i + size] for i in range(0, len(pending), size)]
    saved = 0
    for n, batch in enumerate(batches, 1):
        print(f"\n── batch {n}/{len(batches)} ──", flush=True)
        try:
            results = run_batch(batch)
        except Exception as e:
            print(f"    ❌ batch failed ({type(e).__name__}: {e}) — continuing")
            continue
        for f in batch:
            # Sarvam names each output after the uploaded file.
            key = next((k for k in results if k.startswith(f.name)), None) \
                or next((k for k in results if Path(k).stem.startswith(f.stem)), None)
            if not key:
                print(f"    ⚠ no result returned for {f.name}")
                continue
            r = results[key]
            (OUTDIR / f"{f.stem}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=1))
            (OUTDIR / f"{f.stem}.txt").write_text(plain_text(r), encoding="utf-8")
            saved += 1
            preview = (r.get("transcript") or "")[:90].replace("\n", " ")
            print(f"    ✅ {f.name[:52]:52s} {preview}")

    print(f"\n✅ {saved} voice note(s) transcribed → {OUTDIR}")

    # One combined file so the whole training set can be read in order.
    combined = OUTDIR / "ALL_VOICE_NOTES.md"
    parts = []
    for txt in sorted(OUTDIR.glob("*.txt")):
        parts.append(f"\n\n## {txt.stem}\n\n{txt.read_text(encoding='utf-8')}")
    combined.write_text("# Sameer — training voice notes (Sarvam transcripts)\n"
                        + "".join(parts), encoding="utf-8")
    print(f"📄 combined → {combined}")


if __name__ == "__main__":
    main()
