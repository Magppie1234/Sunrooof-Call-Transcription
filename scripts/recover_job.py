import os
import sys
import json
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discover_zoho import access_token, domains  # noqa: E402
from transcribe_sample import format_transcript, upload_note_to_zoho

try:
    from sarvamai import SarvamAI
    from sarvamai.speech_to_text_job.client import SpeechToTextJobClient
    from sarvamai.speech_to_text_job.job import SpeechToTextJob
except ImportError:
    print("sarvamai SDK not installed.")
    sys.exit(1)

load_dotenv()
OUT = Path(__file__).resolve().parent.parent / "out"

def main() -> int:
    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    client = SarvamAI(api_subscription_key=sarvam_api_key)
    
    accounts, api = domains()
    zoho_headers = {"Authorization": f"Zoho-oauthtoken {access_token(accounts)}"}

    job_id = "20260722_b1b2b9bf-c62f-4063-9af9-8ee755236cc5"
    print(f"Recovering Job: {job_id}")
    
    # Instantiate the job
    job = SpeechToTextJob(job_id=job_id, client=client.speech_to_text_job)
    
    transcripts_dir = OUT / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    
    print("Skipping download since we already have the JSON files.")
    # for attempt in range(3):
    #     try:
    #         job.download_outputs(str(transcripts_dir))
    #         print("Successfully downloaded transcripts!")
    #         break
    #     except Exception as e:
    #         print(f"Attempt {attempt+1} failed: {e}")
    #         time.sleep(5)
    # else:
    #     print("Failed to download outputs after 3 attempts.")
    #     return 1
        
    print("\nProcessing transcripts and uploading Notes to Zoho...")
    # I need to match these back to call IDs. The filenames are {call_id}.mp3.json
    for json_file in transcripts_dir.glob("*.mp3.json"):
        base_name = json_file.name
        call_id = base_name.split(".")[0]
        
        with open(json_file, 'r') as f:
            sarvam_data = json.load(f)
            
        note_content = format_transcript(sarvam_data)
        
        if not note_content.strip() or note_content == "(No transcript available)":
             note_content = "(No speech detected in this recording)"
             
        print(f"\n--- Transcript for Call {call_id} ---")
        print(note_content[:500] + ("..." if len(note_content) > 500 else ""))
        print("--------------------------------------")
        
        upload_note_to_zoho(api, zoho_headers, call_id, note_content)
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
