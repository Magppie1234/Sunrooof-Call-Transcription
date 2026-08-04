import os
import sys
import time
from dotenv import load_dotenv
import json

load_dotenv()
from sarvamai import SarvamAI

def main():
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("SARVAM_API_KEY not found in .env")
        return 1

    client = SarvamAI(api_subscription_key=api_key)
    
    audio_path = "out/1032257000024137220.mp3"
    
    if not os.path.exists(audio_path):
        print(f"File {audio_path} not found.")
        return 1

    print(f"Submitting {audio_path} to Sarvam Batch API using SDK...")
    try:
        job = client.speech_to_text_job.create_job(
            model="saaras:v3",
            mode="translit",
            with_diarization=True
        )
        print(f"Job created: {job.job_id}")
        
        print("Uploading files...")
        job.upload_files([audio_path])
        
        print("Starting job...")
        job.start()
        
        print("Waiting for completion (this could take a few minutes)...")
        status = job.wait_until_complete(poll_interval=5)
        print(f"Job finished with status: {status.job_state}")
        
        if status.job_state.lower() == "completed":
            print("Downloading outputs...")
            os.makedirs("out/transcripts", exist_ok=True)
            job.download_outputs("out/transcripts")
            
            out_file = f"out/transcripts/{os.path.basename(audio_path)}.json"
            if os.path.exists(out_file):
                with open(out_file, "r") as f:
                    data = json.load(f)
                print(json.dumps(data, indent=2))
            else:
                print(f"Output file {out_file} not found.")
        else:
            print("Job did not complete successfully.")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sys.exit(main())
