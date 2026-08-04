import os
import sys
import time
import json
from pathlib import Path
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discover_zoho import access_token, domains  # noqa: E402

try:
    from sarvamai import SarvamAI
except ImportError:
    print("sarvamai SDK not installed.")
    sys.exit(1)

load_dotenv()
OUT = Path(__file__).resolve().parent.parent / "out"

def format_transcript(sarvam_json: dict) -> str:
    diarized = sarvam_json.get("diarized_transcript")
    if diarized and diarized.get("entries"):
        lines = []
        for entry in diarized["entries"]:
            speaker = entry.get("speaker", "Unknown Speaker")
            text = entry.get("transcript", "")
            lines.append(f"{speaker}: {text}")
        return "\n".join(lines)
    else:
        # Fallback to plain transcript if no diarization
        return sarvam_json.get("transcript", "(No transcript available)")

def upload_note_to_zoho(api_domain: str, headers: dict, call_id: str, content: str):
    url = f"{api_domain}/crm/v7/Notes"
    
    # Cap content length if needed (e.g. 30000 chars)
    if len(content) > 30000:
        content = content[:30000] + "\n...[TRUNCATED]"
        
    payload = {
        "data": [
            {
                "Parent_Id": {
                    "id": call_id,
                    "module": {"api_name": "Calls"}
                },
                "Note_Title": "Call Transcript (Sarvam AI)",
                "Note_Content": content
            }
        ]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"Failed to create Note for Call {call_id}: {resp.status_code}")
        print(resp.text)
    else:
        print(f"Successfully added Note to Call {call_id}")

def main() -> int:
    zoho_cookie = os.getenv("ZOHO_COOKIE")
    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    if not zoho_cookie or not sarvam_api_key:
        print("Missing ZOHO_COOKIE or SARVAM_API_KEY in .env")
        return 1

    accounts, api = domains()
    zoho_headers = {"Authorization": f"Zoho-oauthtoken {access_token(accounts)}"}
    sarvam_client = SarvamAI(api_subscription_key=sarvam_api_key)

    # 1. Fetch 5 Calls with recordings
    print("Fetching up to 5 recent Calls with a recording from Zoho API...")
    resp = requests.get(
        f"{api}/crm/v7/Calls",
        params={
            "fields": "id,Voice_Recording__s",
            "per_page": 200,
            "sort_by": "Modified_Time",
            "sort_order": "desc",
        },
        headers=zoho_headers,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Failed to fetch calls: {resp.text}")
        return 1

    records = resp.json().get("data", [])
    calls_with_rec = [r for r in records if r.get("Voice_Recording__s")][:5]
    
    if not calls_with_rec:
        print("No recent calls have a Voice_Recording__s URL.")
        return 1

    OUT.mkdir(exist_ok=True)
    downloaded_files = []
    call_id_map = {} # path -> call_id

    # 2. Download audio
    print(f"\nDownloading audio for {len(calls_with_rec)} calls...")
    req_headers = {
        "Cookie": zoho_cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    for call in calls_with_rec:
        call_id = call["id"]
        rec_url = call["Voice_Recording__s"]
        out_file = OUT / f"{call_id}.mp3"
        
        dl_resp = requests.get(rec_url, headers=req_headers, stream=True, timeout=30)
        if dl_resp.status_code == 200:
            if "html" in dl_resp.headers.get("Content-Type", ""):
                 print(f"❌ Failed to download {call_id}: Got HTML (Cookie expired?)")
                 continue
                 
            with open(out_file, 'wb') as f:
                for chunk in dl_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded_files.append(str(out_file))
            call_id_map[os.path.basename(out_file)] = call_id
            print(f"Downloaded {call_id}.mp3")
        else:
            print(f"❌ Failed to download {call_id}: HTTP {dl_resp.status_code}")
            print(dl_resp.text[:200])

    if not downloaded_files:
        print("No audio files downloaded. Exiting.")
        return 1

    # 3. Submit to Sarvam
    print(f"\nSubmitting {len(downloaded_files)} files to Sarvam Batch API...")
    try:
        job = sarvam_client.speech_to_text_job.create_job(
            model="saaras:v3",
            mode="translit",
            with_diarization=True
        )
        print(f"Job created: {job.job_id}")
        
        job.upload_files(downloaded_files)
        print("Files uploaded.")
        
        job.start()
        print("Job started. Waiting for completion...")
        
        status = job.wait_until_complete(poll_interval=10, timeout=1200)
        print(f"Job finished with status: {status.job_state}")
        
        if status.job_state.lower() != "completed":
            print("Job did not complete successfully.")
            return 1
            
        transcripts_dir = OUT / "transcripts"
        transcripts_dir.mkdir(exist_ok=True)
        job.download_outputs(str(transcripts_dir))
        
    except Exception as e:
        print(f"Error during Sarvam processing: {e}")
        return 1

    # 4. Format and Upload to Zoho
    print("\nProcessing transcripts and uploading Notes to Zoho...")
    for file_path in downloaded_files:
        base_name = os.path.basename(file_path)
        call_id = call_id_map[base_name]
        
        json_file = OUT / "transcripts" / f"{base_name}.json"
        if not json_file.exists():
            print(f"Transcript JSON not found for {base_name}")
            continue
            
        with open(json_file, 'r') as f:
            sarvam_data = json.load(f)
            
        note_content = format_transcript(sarvam_data)
        
        if not note_content.strip() or note_content == "(No transcript available)":
             note_content = "(No speech detected in this recording)"
             
        print(f"\n--- Transcript for Call {call_id} ---")
        print(note_content[:500] + ("..." if len(note_content) > 500 else ""))
        print("--------------------------------------")
        
        upload_note_to_zoho(api, zoho_headers, call_id, note_content)

    print("\n✅ Dry run complete! Please check Zoho CRM to verify the notes.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
