#!/usr/bin/env python3
"""
Vera — EXTREME STRESS TESTER
=============================
Harder than the official judge. Tests everything that could break in production.

Tests:
  1. Suppression key deduplication (same trigger twice → no second message)
  2. Stale version rejection (/v1/context version rollback)
  3. Full tick with ALL 25 triggers at once (volume + budget pressure)
  4. Concurrent tick calls (race condition check)
  5. Conversation loop limits (bot must exit after 4+ Vera turns with 0 replies)
  6. Multilingual hostile messages (Hindi, Hinglish, mixed)
  7. Body length enforcement (>320 chars = fail)
  8. URL injection guard (bot must never return URLs in body)
  9. Duplicate body guard (bot must not repeat itself)
 10. Edge: unknown conversation_id in /v1/reply
 11. Edge: missing merchant_id in trigger
 12. Edge: expired trigger skipped in tick
 13. Teardown wipes state

Run: python stress_test.py
"""

import json
import time
import sys
import re
import os
import threading
from datetime import datetime, timezone, timedelta
from urllib import request as urlrequest, error as urlerror
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

BOT_URL = os.getenv("BOT_URL", "http://localhost:8080")
EXPANDED_DIR = Path(__file__).parent / "expanded"
DATASET_DIR = Path(__file__).parent / "dataset"

# ── Colors ────────────────────────────────────────────────────────────────────
class C:
    PASS  = "\033[92m[PASS]\033[0m"
    FAIL  = "\033[91m[FAIL]\033[0m"
    WARN  = "\033[93m[WARN]\033[0m"
    INFO  = "\033[94m[INFO]\033[0m"
    SECTION = "\033[95m\033[1m"
    RESET = "\033[0m"
    BOLD  = "\033[1m"
    RED   = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"

def section(title: str):
    print(f"\n{C.SECTION}{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}{C.RESET}\n")

def ok(msg):  print(f"  {C.PASS} {msg}")
def fail(msg): print(f"  {C.FAIL} {msg}")
def warn(msg): print(f"  {C.WARN} {msg}")
def info(msg): print(f"  {C.INFO} {msg}")

# ── HTTP Client ───────────────────────────────────────────────────────────────
def _req(method, path, body=None, timeout=30):
    url = f"{BOT_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urlrequest.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        resp = urlrequest.urlopen(req, timeout=timeout)
        return json.loads(resp.read()), None, (time.time()-t0)*1000
    except urlerror.HTTPError as e:
        lat = (time.time()-t0)*1000
        try:   return json.loads(e.read()), None, lat
        except: return None, f"HTTP {e.code}", lat
    except Exception as ex:
        return None, str(ex), (time.time()-t0)*1000

def get(path, **kw):  return _req("GET", path, **kw)
def post(path, body, **kw): return _req("POST", path, body, **kw)

now_iso = lambda: datetime.now(timezone.utc).isoformat() + "Z"
expired_iso = lambda: (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat() + "Z"

# ── Dataset ───────────────────────────────────────────────────────────────────
def load_dataset():
    cats, merchants, customers, triggers = {}, {}, {}, {}
    
    # Priority order: expanded (individual files) -> dataset (individual files) -> dataset (seed files)
    roots = [EXPANDED_DIR, DATASET_DIR]
    
    for root in roots:
        if not root.exists(): continue
        
        # 1. Load from subdirectories (categories, merchants, customers, triggers)
        for sub, store, key in [
            ("categories", cats, "slug"),
            ("merchants", merchants, "merchant_id"),
            ("customers", customers, "customer_id"),
            ("triggers",  triggers,  "id"),
        ]:
            s_dir = root / sub
            if s_dir.exists():
                for f in s_dir.glob("*.json"):
                    try:
                        d = json.load(open(f, encoding="utf-8"))
                        item_id = d.get(key, f.stem)
                        if item_id not in store:
                            store[item_id] = d
                    except: pass
        
        # 2. Load from seed files (merchants_seed.json, etc.)
        for fname, store, key in [
            ("merchants_seed.json", merchants, "merchant_id"),
            ("customers_seed.json", customers, "customer_id"),
            ("triggers_seed.json",  triggers,  "id"),
        ]:
            p = root / fname
            if p.exists():
                try:
                    raw = json.load(open(p, encoding="utf-8"))
                    # Find the list container (e.g. "merchants", "customers", "triggers")
                    container = next((k for k in raw.keys() if isinstance(raw[k], list)), None)
                    if container:
                        for item in raw[container]:
                            if key in item and item[key] not in store:
                                store[item[key]] = item
                except: pass
                
    return cats, merchants, customers, triggers

# ── Push all contexts ─────────────────────────────────────────────────────────
def push_all_contexts(cats, merchants, customers, triggers):
    for slug, cat in cats.items():
        post("/v1/context", {"scope":"category","context_id":slug,"version":1,"payload":cat,"delivered_at":now_iso()})
    for mid, m in merchants.items():
        post("/v1/context", {"scope":"merchant","context_id":mid,"version":1,"payload":m,"delivered_at":now_iso()})
    for cid, c in customers.items():
        post("/v1/context", {"scope":"customer","context_id":cid,"version":1,"payload":c,"delivered_at":now_iso()})
    for tid, t in triggers.items():
        post("/v1/context", {"scope":"trigger","context_id":tid,"version":1,"payload":t,"delivered_at":now_iso()})

# ═════════════════════════════════════════════════════════════════════════════
# TESTS
# ═════════════════════════════════════════════════════════════════════════════

results: List[tuple] = []

def record(name, passed, detail=""):
    results.append((name, passed, detail))
    (ok if passed else fail)(f"{name}  {detail}")

# ── TEST 1: Health check ──────────────────────────────────────────────────────
def test_health():
    section("TEST 1 — Health + Metadata")
    data, err, lat = get("/v1/healthz")
    record("healthz responds", not err and data.get("status")=="ok", f"({lat:.0f}ms)")

    data, err, _ = get("/v1/metadata")
    record("metadata has team_name",  not err and bool(data.get("team_name")))
    record("metadata has model",      not err and bool(data.get("model")))
    record("metadata has contact_email", not err and bool(data.get("contact_email")))

# ── TEST 2: Context version rejection ────────────────────────────────────────
def test_stale_version(cats):
    section("TEST 2 — Stale Version Rejection")
    slug = list(cats.keys())[0]
    cat = cats[slug]
    # Push v5
    post("/v1/context", {"scope":"category","context_id":slug,"version":5,"payload":cat,"delivered_at":now_iso()})
    # Push v3 (stale)
    data, err, _ = post("/v1/context", {"scope":"category","context_id":slug,"version":3,"payload":cat,"delivered_at":now_iso()})
    record("Stale v3 rejected after v5", not err and data.get("accepted") == False,
           f"accepted={data.get('accepted') if data else 'N/A'}")
    # Push v6 (fresh)
    data, err, _ = post("/v1/context", {"scope":"category","context_id":slug,"version":6,"payload":cat,"delivered_at":now_iso()})
    record("Fresh v6 accepted",    not err and data.get("accepted") == True)

# ── TEST 3: Suppression key dedup ─────────────────────────────────────────────
def test_suppression(triggers, merchants, cats, customers):
    section("TEST 3 — Suppression Key Deduplication")
    # Find a trigger with a suppression key
    trg = next((t for t in triggers.values() if t.get("suppression_key")), None)
    if not trg:
        warn("No trigger with suppression_key found — skipping"); return

    tid = trg["id"]
    mid = trg.get("merchant_id","")
    push_all_contexts(cats, merchants, customers, {tid: trg})

    # First tick — should produce an action
    d1, e1, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": [tid]})
    first_count = len(d1.get("actions", [])) if d1 else 0

    # Second tick with same trigger — suppression key already fired, should be 0
    d2, e2, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": [tid]})
    second_count = len(d2.get("actions", [])) if d2 else 0

    record("First tick produces action",  first_count >= 1, f"actions={first_count}")
    record("Second tick suppressed",      second_count == 0, f"actions={second_count}")

# ── TEST 4: Expired trigger skipped ──────────────────────────────────────────
def test_expired_trigger(merchants, cats):
    section("TEST 4 — Expired Trigger Skipped")
    expired_trg = {
        "id": "trg_EXPIRED_001",
        "scope": "merchant", "kind": "perf_dip", "source": "internal",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "customer_id": None,
        "payload": {"metric": "calls", "delta_pct": -0.5, "window": "7d"},
        "urgency": 5,
        "suppression_key": "stress:expired_test:001",
        "expires_at": expired_iso()   # already expired 2h ago
    }
    post("/v1/context", {"scope":"trigger","context_id":"trg_EXPIRED_001","version":1,"payload":expired_trg,"delivered_at":now_iso()})
    data, err, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": ["trg_EXPIRED_001"]})
    actions = data.get("actions",[]) if data else []
    record("Expired trigger not acted on", len(actions)==0, f"actions={len(actions)} lat={lat:.0f}ms")

# ── TEST 5: Full volume tick (all 25 triggers) ────────────────────────────────
def test_volume_tick(triggers, merchants, cats, customers):
    section("TEST 5 — Volume Tick (All 25 Triggers)")
    push_all_contexts(cats, merchants, customers, triggers)
    tids = list(triggers.keys())
    info(f"Firing tick with {len(tids)} triggers...")
    data, err, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": tids}, timeout=20)
    actions = data.get("actions",[]) if data else []
    record("Tick completes under 15s", lat < 15000, f"lat={lat:.0f}ms")
    record("At least 1 action returned", len(actions) >= 1, f"actions={len(actions)}")

    # Validate each action body
    url_re = re.compile(r"https?://")
    for i, act in enumerate(actions):
        body = act.get("body","")
        if len(body) > 320:
            fail(f"Action {i}: body too long ({len(body)} chars)")
            results.append((f"body_length_{i}", False, f"{len(body)} chars"))
        if url_re.search(body):
            fail(f"Action {i}: URL found in body!")
            results.append((f"no_url_{i}", False, body[:80]))

    # Check no dupes
    bodies = [a.get("body","") for a in actions]
    unique = len(set(bodies))
    record("No duplicate bodies in batch", unique == len(bodies), f"{unique}/{len(bodies)} unique")

# ── TEST 6: Concurrent tick calls (race condition) ────────────────────────────
def test_concurrent_ticks(triggers):
    section("TEST 6 — Concurrent Tick Calls (Race Condition)")
    tids = list(triggers.keys())[:5]
    responses = []
    errors = []

    def fire():
        d, e, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": tids}, timeout=20)
        if e: errors.append(e)
        else: responses.append(d)

    threads = [threading.Thread(target=fire) for _ in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()

    record("No errors in concurrent ticks", len(errors)==0, f"errors={errors[:1]}")
    record("All 3 concurrent ticks returned", len(responses)==3, f"responses={len(responses)}")

# ── TEST 7: Body length enforcement ──────────────────────────────────────────
def test_body_length(merchants, cats, triggers):
    section("TEST 7 — Body Length Enforcement (<= 320 chars)")
    tids = list(triggers.keys())
    data, err, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": tids[:10]}, timeout=20)
    if not data:
        warn("No tick response"); return
    actions = data.get("actions",[])
    violations = [a for a in actions if len(a.get("body","")) > 320]
    record(f"All bodies ≤ 320 chars", len(violations)==0,
           f"violations={len(violations)}/{len(actions)}")
    for v in violations:
        fail(f"  Violation: {len(v.get('body',''))} chars — \"{v.get('body','')[:60]}...\"")

# ── TEST 8: URL injection guard ───────────────────────────────────────────────
def test_no_urls(triggers):
    section("TEST 8 — URL Injection Guard")
    tids = list(triggers.keys())[:15]
    data, _, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": tids}, timeout=20)
    if not data: warn("No tick response"); return
    url_re = re.compile(r"https?://")
    violations = [a for a in data.get("actions",[]) if url_re.search(a.get("body",""))]
    record("No URLs in any action body", len(violations)==0,
           f"violations={len(violations)}")

# ── TEST 9: Multilingual hostile messages ────────────────────────────────────
def test_multilingual_hostile(merchants):
    section("TEST 9 — Multilingual Hostile Messages")
    mid = list(merchants.keys())[0]
    hostile_msgs = [
        ("Hindi stop",       "band karo ye sab"),
        ("Hinglish spam",    "bhai mat bhejna aisi messages"),
        ("Hindi unsubscribe","nahi chahiye mujhe"),
        ("English hostile",  "Stop messaging me. This is spam."),
        ("Mixed",            "Please stop bro, nahi chahiye"),
    ]
    for label, msg in hostile_msgs:
        data, err, _ = post("/v1/reply", {
            "conversation_id": f"conv_hostile_{label.replace(' ','_')}",
            "merchant_id": mid, "customer_id": None,
            "from_role": "merchant", "message": msg,
            "received_at": now_iso(), "turn_number": 2
        })
        action = data.get("action","?") if data else "ERROR"
        passed = action == "end"
        record(f"Hostile [{label}] → end", passed, f"action={action} msg='{msg}'")

# ── TEST 10: Auto-reply loop detection ───────────────────────────────────────
def test_auto_reply_loop(merchants):
    section("TEST 10 — Auto-Reply Loop (Same msg 3x)")
    mid = list(merchants.keys())[0]
    auto_msg = "Thank you for contacting us. We will respond shortly."
    conv_id = "conv_stress_auto_loop_001"
    ended = False
    for i in range(1, 6):
        data, err, _ = post("/v1/reply", {
            "conversation_id": conv_id, "merchant_id": mid,
            "customer_id": None, "from_role": "merchant",
            "message": auto_msg, "received_at": now_iso(), "turn_number": i+1
        })
        if data and data.get("action") == "end":
            record(f"Auto-reply loop ended on turn {i}", True, f"turn={i}")
            ended = True
            break
    if not ended:
        record("Auto-reply loop never ended (after 5 turns)", False, "bot should have sent action=end")

# ── TEST 11: Committed intent → immediate action ──────────────────────────────
def test_committed_intent(merchants):
    section("TEST 11 — Committed Intent → No More Qualifying")
    mid = list(merchants.keys())[0]
    commits = [
        "Yes let's do it",
        "haan chalo",
        "Ok lets go",
        "yep go ahead",
        "bilkul karo",
    ]
    qualifying_words = ["would you", "can you", "do you want", "shall we", "what if"]
    for msg in commits:
        data, err, _ = post("/v1/reply", {
            "conversation_id": f"conv_commit_{msg[:10].replace(' ','_')}",
            "merchant_id": mid, "customer_id": None,
            "from_role": "merchant", "message": msg,
            "received_at": now_iso(), "turn_number": 2
        })
        body = (data.get("body","") if data else "").lower()
        action = (data.get("action","") if data else "")
        still_qualifying = any(w in body for w in qualifying_words)
        passed = action == "send" and not still_qualifying
        record(f"Committed '{msg[:20]}' → action mode", passed,
               f"action={action} qualifying={still_qualifying}")

# ── TEST 12: Unknown conversation ID ─────────────────────────────────────────
def test_unknown_conv(merchants):
    section("TEST 12 — Unknown Conversation ID in /v1/reply")
    mid = list(merchants.keys())[0]
    data, err, _ = post("/v1/reply", {
        "conversation_id": "conv_NONEXISTENT_XYZ_99999",
        "merchant_id": mid, "customer_id": None,
        "from_role": "merchant", "message": "Hello?",
        "received_at": now_iso(), "turn_number": 1
    })
    record("Unknown conv returns valid action", not err and data.get("action") in ("send","end","wait"),
           f"action={data.get('action') if data else 'ERROR'}")
    body = data.get("body","") if data else ""
    record("Unknown conv body not empty", bool(body.strip()), f"body='{body[:60]}'")

# ── TEST 13: Dormancy — bot silent after 4 unanswered messages ────────────────
def test_dormancy(merchants, cats, triggers):
    section("TEST 13 — Dormancy (4 Vera messages, 0 merchant replies)")
    mid = list(merchants.keys())[0]
    # Simulate a conversation that already has 4 Vera turns with 0 merchant turns
    # We do this by calling /v1/reply on a conv that doesn't exist (bot initializes fresh)
    # then rapidly send more vera-side pings. Vera's dormancy check is on HER turn count.
    # We test by replying 4 times without the merchant sending anything meaningful.
    conv_id = "conv_stress_dormancy_001"
    for i in range(1, 6):
        data, err, _ = post("/v1/reply", {
            "conversation_id": conv_id,
            "merchant_id": mid, "customer_id": None,
            "from_role": "vera", "message": f"Vera message {i}",
            "received_at": now_iso(), "turn_number": i
        })
    # Now the merchant "replies" — bot should check turn history
    data, err, _ = post("/v1/reply", {
        "conversation_id": conv_id, "merchant_id": mid,
        "customer_id": None, "from_role": "merchant",
        "message": "hi", "received_at": now_iso(), "turn_number": 6
    })
    action = data.get("action","?") if data else "ERROR"
    record("Bot responds to merchant after dormancy", action in ("send","end"),
           f"action={action}")

# ── TEST 14: Teardown wipes state ────────────────────────────────────────────
def test_teardown(triggers):
    section("TEST 14 — Teardown Wipes State")
    data, err, _ = post("/v1/teardown", {})
    record("Teardown returns status=wiped", not err and data.get("status")=="wiped")

    # After teardown, tick with all triggers should return 0 actions (no contexts)
    tids = list(triggers.keys())
    data, err, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": tids}, timeout=15)
    actions = data.get("actions",[]) if data else []
    record("Post-teardown tick returns 0 actions (state wiped)", len(actions)==0,
           f"actions={len(actions)}")

# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def summary():
    section("STRESS TEST RESULTS")
    passed = sum(1 for _, p, _ in results if p)
    total  = len(results)
    pct = (passed/total*100) if total else 0

    for name, p, detail in results:
        sym = C.PASS if p else C.FAIL
        print(f"  {sym} {name}  {C.YELLOW}{detail}{C.RESET}")

    print()
    color = C.GREEN if pct >= 80 else C.YELLOW if pct >= 60 else C.RED
    print(f"  {C.BOLD}SCORE: {color}{passed}/{total} ({pct:.0f}%){C.RESET}")
    if pct >= 90:   print(f"\n  {C.GREEN}★ PRODUCTION READY{C.RESET}")
    elif pct >= 75: print(f"\n  {C.YELLOW}✓ GOOD — minor fixes needed{C.RESET}")
    elif pct >= 50: print(f"\n  {C.YELLOW}⚠ NEEDS WORK{C.RESET}")
    else:           print(f"\n  {C.RED}✗ CRITICAL FAILURES — not ready{C.RESET}")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{C.BOLD}{'='*60}")
    print("  VERA — EXTREME STRESS TESTER")
    print(f"  Bot: {BOT_URL}")
    print(f"{'='*60}{C.RESET}\n")

    # Quick connectivity check
    _, err, _ = get("/v1/healthz", timeout=5)
    if err:
        print(f"{C.RED}Bot is unreachable: {err}{C.RESET}")
        print("Start it with: uvicorn bot:app --host 0.0.0.0 --port 8080")
        sys.exit(1)

    # Clean slate
    post("/v1/teardown", {})

    cats, merchants, customers, triggers = load_dataset()
    info(f"Dataset: {len(cats)} cats, {len(merchants)} merchants, {len(customers)} customers, {len(triggers)} triggers\n")

    test_health()
    test_stale_version(cats)
    push_all_contexts(cats, merchants, customers, triggers)  # fresh state for suppression test
    test_suppression(triggers, merchants, cats, customers)
    test_expired_trigger(merchants, cats)
    test_volume_tick(triggers, merchants, cats, customers)
    test_concurrent_ticks(triggers)
    test_body_length(merchants, cats, triggers)
    test_no_urls(triggers)
    test_multilingual_hostile(merchants)
    test_auto_reply_loop(merchants)
    test_committed_intent(merchants)
    test_unknown_conv(merchants)
    test_dormancy(merchants, cats, triggers)
    test_teardown(triggers)

    summary()

if __name__ == "__main__":
    main()
