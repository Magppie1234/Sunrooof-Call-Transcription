import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discover_zoho import access_token, domains  # noqa: E402

load_dotenv()

OUT = Path(__file__).resolve().parent.parent / "out"

def main() -> int:
    accounts, api = domains()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token(accounts)}"}

    zoho_cookie = os.getenv("ZOHO_COOKIE")
    if not zoho_cookie:
        print("Error: ZOHO_COOKIE not found in .env. Please copy your browser cookie and paste it there.")
        return 1

    print("Fetching recent Calls with a recording from Zoho API...")
    resp = requests.get(
        f"{api}/crm/v7/Calls",
        params={
            "fields": "id,Voice_Recording__s",
            "per_page": 200,
            "sort_by": "Modified_Time",
            "sort_order": "desc",
        },
        headers=headers,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Failed to fetch calls: {resp.text}")
        return 1

    records = resp.json().get("data", [])
    call_with_rec = None
    for r in records:
        if r.get("Voice_Recording__s"):
            call_with_rec = r
            break
            
    if not call_with_rec:
        print("No recent calls have a Voice_Recording__s URL.")
        return 1

    rec_url = call_with_rec["Voice_Recording__s"]
    call_id = call_with_rec["id"]
    print(f"Found recording URL for Call {call_id}:")
    print(f"  {rec_url}")
    
    print("\nAttempting to download using browser cookie...")
    OUT.mkdir(exist_ok=True)
    out_file = OUT / f"{call_id}.mp3"
    
    # We pass the user's browser cookie to bypass the API limitation
    req_headers = {
        "Cookie": zoho_cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }

    dl_resp = requests.get(rec_url, headers=req_headers, stream=True, timeout=30)
    
    if dl_resp.status_code == 200:
        content_type = dl_resp.headers.get("Content-Type", "")
        # Even if auth fails, Zoho might return a 200 HTML login page. Check content type.
        if "html" in content_type:
             print(f"❌ Failed: Downloaded an HTML page instead of audio. Your cookie might be expired or incomplete.")
             out_file.write_bytes(dl_resp.content)
             print(f"  Saved to {out_file} so you can see the error page.")
             return 1
             
        with open(out_file, 'wb') as f:
            for chunk in dl_resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_mb = out_file.stat().st_size / (1024 * 1024)
        print(f"✅ Success! Downloaded {size_mb:.2f} MB audio file to: {out_file}")
        return 0
    else:
        print(f"❌ Failed to download. HTTP {dl_resp.status_code}")
        print(dl_resp.text[:200])
        return 1

if __name__ == "__main__":
    sys.exit(main())
