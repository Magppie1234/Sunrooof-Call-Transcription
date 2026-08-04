import os
import sys
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

def main():
    api_key = os.getenv("OZONETEL_API_KEY")
    username = os.getenv("OZONETEL_USERNAME")
    
    if not api_key or not username:
        print("Error: OZONETEL_API_KEY or OZONETEL_USERNAME not found in .env")
        return 1

    domains = [
        "https://in1-ccaas-api.ozonetel.com",
        "https://api.ccaas.ozonetel.com"
    ]
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    params = {
        "apiKey": api_key,
        "userName": username,
        "fromDate": today,
        "toDate": today,
        "format": "json"
    }

    print(f"Testing Ozonotel Authentication for user: {username}")
    
    success = False
    for domain in domains:
        url = f"{domain}/ca_reports/fetchCDRDetails"
        print(f"\nTrying {url}...")
        try:
            headers = {'Content-Type': 'application/json'}
            resp = requests.post(url, json=params, headers=headers, timeout=10)
            print(f"Status Code: {resp.status_code}")
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"Response snippet: {str(data)[:300]}")
                    if isinstance(data, dict) and data.get("status", "").lower() == "error":
                        print("❌ Authentication failed or error returned.")
                    else:
                        print("✅ SUCCESS: API Key and Username are correct! This domain works.")
                        success = True
                        break
                except Exception:
                    print(f"Response text snippet: {resp.text[:300]}")
            else:
                 print(f"Response text snippet: {resp.text[:300]}")
        except Exception as e:
            print(f"Failed to connect: {e}")

    if not success:
        print("\n❌ Failed to authenticate. We might need TOKEN_AUTH or the API key/username is wrong.")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
