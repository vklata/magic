import os, asyncio, json, time
import httpx
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv()

# Check for various possible keys
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()

MODEL_LADDER = [
    # ── Tier 1: Mistral Small (1B tokens/month, most reliable total quota) ──
    {"provider": "mistral",   "model": "mistral-small-latest"},

    # ── Tier 2: Groq Llama 70b (fastest speed, ~1000 req/day free) ──────────
    {"provider": "groq",      "model": "llama-3.3-70b-versatile"},

    # ── Tier 3: Mistral Medium (separate pool, 60K TPM, no monthly cap) ─────
    {"provider": "mistral",   "model": "mistral-medium-2505"},

    # ── Tier 4: Groq 8b (fast, shares Groq quota pool) ──────────────────────
    {"provider": "groq",      "model": "llama-3.1-8b-instant"},

    # ── Tier 5: OpenRouter Llama 70b (free fallback) ─────────────────────────
    {"provider": "openrouter","model": "meta-llama/llama-3.3-70b-instruct:free"},

    # ── Tier 6: OpenRouter Gemini Flash Lite (15 RPM free) ───────────────────
    {"provider": "openrouter","model": "google/gemini-2.0-flash-lite-preview-02-05:free"},
]

async def call_groq(model: str, system: str, user: str):
    if not GROQ_KEY:
        return "MISSING_KEY", 0
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], 200
            return r.text, r.status_code
        except Exception as e:
            return str(e), -1

async def call_openrouter(model: str, system: str, user: str):
    if not OPENROUTER_KEY:
        return "MISSING_KEY", 0
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://magicpin.com",
        "X-Title": "Vera Test"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"System: {system}\n\nUser: {user}"}],
        "temperature": 0
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], 200
            return r.text, r.status_code
        except Exception as e:
            return str(e), -1

async def call_mistral(model: str, system: str, user: str):
    if not MISTRAL_KEY:
        return "MISSING_KEY", 0
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], 200
            return r.text, r.status_code
        except Exception as e:
            return str(e), -1

async def test_ladder():
    print("=== MODEL LADDER DIAGNOSTIC (Excluding OpenAI) ===")
    print(f"GROQ_API_KEY:       {'[FOUND]' if GROQ_KEY else '[MISSING]'}")
    print(f"OPENROUTER_API_KEY: {'[FOUND]' if OPENROUTER_KEY else '[MISSING]'}")
    print(f"MISTRAL_API_KEY:    {'[FOUND]' if MISTRAL_KEY else '[MISSING]'}")
    print("-" * 40)

    for entry in MODEL_LADDER:
        provider = entry["provider"]
        model = entry["model"]
        print(f"Trying {provider.upper()} ({model})...")
        
        t0 = time.time()
        if provider == "groq":
            res, status = await call_groq(model, "You are a tester.", "Say 'Groq OK'")
        elif provider == "mistral":
            res, status = await call_mistral(model, "You are a tester.", "Say 'Mistral OK'")
        else:
            res, status = await call_openrouter(model, "You are a tester.", "Say 'OpenRouter OK'")
        
        dt = time.time() - t0
        if status == 200:
            print(f"  SUCCESS: {res.strip()} ({dt:.2f}s)")
        elif status == 0:
            print(f"  SKIPPED: Key is missing in .env")
        else:
            print(f"  FAILED: Status {status}")
            print(f"  Error: {res[:200]}")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(test_ladder())
