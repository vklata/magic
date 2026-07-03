import json, time
from urllib import request as urlrequest

BOT_URL = "https://kkalra-vera-magicpin.hf.space"

def post(path, body):
    req = urlrequest.Request(f"{BOT_URL}{path}", data=json.dumps(body).encode(), 
                              headers={"Content-Type": "application/json"})
    return json.loads(urlrequest.urlopen(req).read().decode())

def run_test():
    print("--- 1. Wiping state ---")
    post("/v1/teardown", {})

    print("--- 2. Pushing Contexts ---")
    # Using a unique suppression key to avoid any external interference
    unique_sk = f"test_sk_{int(time.time())}"
    
    # Push minimal required context with required delivered_at field
    post("/v1/context", {"scope": "category", "context_id": "dentists", "version": 1, "payload": {"slug": "dentists"}, "delivered_at": "2026-04-29T19:00:00Z"})
    post("/v1/context", {"scope": "merchant", "context_id": "m1", "version": 1, "payload": {"merchant_id": "m1", "category_slug": "dentists", "identity": {"name": "Test Store"}}, "delivered_at": "2026-04-29T19:00:00Z"})
    post("/v1/context", {"scope": "trigger", "context_id": "t1", "version": 1, "payload": {
        "id": "t1", "merchant_id": "m1", "kind": "perf_dip", "urgency": 5, "suppression_key": unique_sk
    }, "delivered_at": "2026-04-29T19:00:00Z"})

    print(f"--- 3. First Tick (Key: {unique_sk}) ---")
    r1 = post("/v1/tick", {"now": "2026-04-29T19:00:00Z", "available_triggers": ["t1"]})
    actions1 = len(r1.get("actions", []))
    print(f"Actions returned: {actions1}")

    print("--- 4. Second Tick (Should be suppressed) ---")
    r2 = post("/v1/tick", {"now": "2026-04-29T19:00:00Z", "available_triggers": ["t1"]})
    actions2 = len(r2.get("actions", []))
    print(f"Actions returned: {actions2}")

    if actions1 == 1 and actions2 == 0:
        print("\n✅ SUCCESS: Logic verified. Bot sends once and then suppresses.")
    else:
        print("\n❌ FAILED: Check bot.py logic.")

if __name__ == "__main__":
    run_test()
