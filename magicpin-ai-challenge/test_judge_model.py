import os
import json
from urllib import request as urlrequest
from dotenv import load_dotenv
from pathlib import Path

# Load .env from root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "meta-llama/llama-3.3-70b-instruct:free"

def test_connection():
    print(f"Testing {MODEL}...")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://magicpin.com"
    }
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict judge."},
            {"role": "user", "content": "Score this message from 1-10: 'Hello, how can I help you today?'"}
        ],
        "max_tokens": 50
    }).encode("utf-8")

    req = urlrequest.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers=headers
    )

    try:
        resp = urlrequest.urlopen(req, timeout=15)
        res_json = json.loads(resp.read().decode("utf-8"))
        content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"SUCCESS: {content}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

if __name__ == "__main__":
    if not API_KEY:
        print("Error: OPENROUTER_API_KEY not found in .env")
    else:
        test_connection()
