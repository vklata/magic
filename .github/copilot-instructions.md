# Copilot Instructions — Vera (magicpin AI Challenge)

> **Deadline: 02 May 2026, 11:59 PM IST**
> Bot must stay live for 72h post-deadline. Judge harness runs fresh scenarios until ~05 May.
> Solo applications only. Full-time role, Gurgaon.

***

## Prime Directive

**The judge scores decisions, not writing style.**

A generic message with a merchant name injected is still generic.
Every output must be driven by real numbers from the context received in that request.
There are no shortcuts — the real judge injects fresh digest items, new metric shifts,
and surprise trigger kinds that the simulator never showed you.

> "Bots that pattern-match the simulator will fail.
>  Bots that ground every output in the context they've been given will not."

***

## Required Endpoints

3 consecutive `/healthz` failures = **disqualified**.

| Method | Path | Contract |
|--------|------|----------|
| POST | `/v1/context` | Store category/merchant/trigger/customer JSON. Idempotent by scope+version. |
| POST | `/v1/tick` | Decide triggers → return ≤20 actions within 30s |
| POST | `/v1/reply` | Handle merchant/customer reply → return send/wait/end within 30s |
| GET | `/v1/healthz` | Always return `{"status":"ok","uptime_seconds":N,"contexts_loaded":N}` |
| GET | `/v1/metadata` | Return `{"team_name":"...","model":"...","approach":"...","version":"..."}` |

**Hard constraints:**
- 30s max response per request
- 10 req/sec sustained load from judge
- 500 KB context payload cap
- ≤20 actions per `/v1/tick` response
- `temperature: 0` on ALL LLM calls — never change this

***

## In-Memory State (No Database)

```python
contexts: dict[tuple[str,str], dict]  # (scope, id) → {version, payload, stored_at}
conversations: dict[str, dict]         # conv_id → {turns, intent, state}
suppression_sent: set[str]             # global dedup — never re-send same key
hostile_merchants: set[str]            # merchants who opted out
```

Server restart = state loss. This is acceptable for the 60-min test window.
**Never use localStorage, SQLite, or Redis** — in-memory only.

***

## 4-Context Composition Engine

Every message is composed from exactly these layers:

```python
compose(category, merchant, trigger, customer=None)
```

| Layer | Source | Provides |
|-------|--------|---------|
| **Category** | `categories/{slug}.json` | vocab_allowed, vocab_taboo, peer benchmarks, digest items |
| **Merchant** | `merchants/{id}.json` | owner_first_name, locality, CTR, offers, aggregates, signals |
| **Trigger** | `triggers/{id}.json` | Why NOW — kind, urgency, payload, expires_at, suppression_key |
| **Customer** | `customers/{id}.json` (optional) | name, language, slot prefs, relationship state |

***

## Model Ladder

```python
GROQ_KEY       = os.getenv("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

MODEL_LADDER = [
    # Tier 1 — Groq primary: fast, 6000 tokens/min free
    ("groq",        "llama-3.3-70b-versatile"),

    # Tier 2 — OpenRouter Gemini: cross to different provider on Groq 429
    # NEVER put another Groq model here — same org quota pool = instant 429
    ("openrouter",  "google/gemini-2.0-flash-exp:free"),

    # Tier 3 — Groq 8b: separate model quota (14,400 req/day)
    ("groq",        "llama-3.1-8b-instant"),

    # Tier 4 — OpenRouter free fallback
    ("openrouter",  "google/gemma-3-27b-it:free"),

    # Tier 5 — Last resort
    ("openrouter",  "openrouter/auto"),
]

# LLM call settings — do not change
MAX_TOKENS  = 180   # 320 chars ≈ 120 tokens; 180 is the safe ceiling
TEMPERATURE = 0     # determinism required by judge
BUDGET_SECS = 7.0   # total per compose call
```

### call_llm_ladder — Correct Implementation

```python
async def llm_call(provider: str, model: str, system: str, user: str,
                   timeout: float) -> tuple[str, int]:
    if provider == "groq":
        if not GROQ_KEY: return "", 0
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}",
                   "Content-Type": "application/json"}
    else:
        if not OPENROUTER_KEY: return "", 0
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENROUTER_KEY}",
                   "Content-Type": "application/json",
                   "HTTP-Referer": "https://magicpin.com",
                   "X-Title": "Vera Merchant Assistant"}

    body = {"model": model, "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": user}]}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(max(1.0, timeout), connect=2.0)
    ) as client:
        try:
            r = await client.post(url, headers=headers, json=body)
            if r.status_code == 200:
                content = (r.json().get("choices",[{}])[0]
                            .get("message",{}).get("content",""))
                return content or "", 200
            logger.warning(f"[LLM] {provider}/{model} {r.status_code}: {r.text[:120]}")
            return "", r.status_code
        except Exception as e:
            logger.error(f"[LLM] {provider}/{model} error: {e}")
            return "", 0


async def call_llm_ladder(system: str, user: str,
                          budget: float = BUDGET_SECS) -> str:
    if not GROQ_KEY and not OPENROUTER_KEY:
        return '{"body":"","cta":"open_ended","rationale":"missing-api-keys"}'

    t0 = time.time()
    for i, (provider, model) in enumerate(MODEL_LADDER):
        remaining = budget - (time.time() - t0)
        if remaining < 1.2:
            logger.warning(f"[LLM] Budget exhausted at tier {i+1}")
            break

        tier_timeout = min(2.2 if provider == "groq" else 3.0, remaining - 0.3)
        text, status = await llm_call(provider, model, system, user, tier_timeout)

        if status == 200 and text:
            logger.info(f"[LLM] OK tier {i+1}: {provider}/{model} "
                        f"({time.time()-t0:.2f}s)")
            return text

        if status == 429:
            # Never retry same model — move on immediately
            logger.warning(f"[LLM] 429 {provider}/{model} → next tier")
            await asyncio.sleep(0.3)
            continue

        if status == 400:
            # Decommissioned model — skip instantly, no sleep
            logger.warning(f"[LLM] 400 {provider}/{model} → skipping")
            continue

    logger.error("[LLM] All tiers exhausted — grounded fallback will fire")
    return '{"body":"","cta":"open_ended","rationale":"all-tiers-failed"}'
```

**Why this structure:**
- Tier 1 → Tier 2 crosses providers on 429 (Groq → OR) — avoids shared quota
- Tier 3 uses `llama-3.1-8b-instant` which has a **separate** Groq model quota
- `llama-3.1-70b-versatile` is **decommissioned** — never add it back (400 error)
- 0.3s sleep on 429 (not 1s) — preserves budget for real fallback
- Hard `remaining < 1.2` guard ensures `build_grounded_fallback()` always has time

***

## Message Composition Flow

### Step 1 — extract_grounding_facts()

Pull ALL real facts into a flat dict. The LLM uses ONLY these — hallucination impossible.

**Critical field that must be present:**
```python
"_raw_digest": digest,   # full list — enables regulation_change to match by item ID
                          # WITHOUT this, regulation_change always uses wrong title → 18/50
```

Fields to extract:
```
owner_name, locality, city, languages, category_slug
views_30d, calls_30d, ctr, leads_30d, delta_7d, ctr_gap, signals
plan, days_remaining
total_customers, lapsed_customers, retention_6mo, high_risk_adult_count
active_offers, paused_offers
digest_title, digest_source, digest_trial_n, digest_segment, _raw_digest
trend_query, trend_delta
trigger_kind, trigger_payload, trigger_urgency
customer_name, customer_last_visit, customer_state, customer_slots
peer_ctr, peer_avg_rating, peer_scope
```

### Step 2 — build_message_plan()

Deterministic pre-LLM plan. Decides BEFORE the LLM:

```python
plan = {
    "angle":              "",   # narrative direction
    "anchor_facts":       [],   # facts LLM MUST include — need ≥3 with numbers
    "decision_statement": "",   # ONE decision merchant must make TODAY
    "compulsion_lever":   "",   # loss_aversion / effort_externalization / curiosity / social_proof
    "cta_shape":          "binary",  # binary / open_ended / none
    "tone":               "",   # derived from category_slug
}
```

**decision_statement by trigger kind:**
```
renewal_due          → f"Decide: renew in {days} days or listings go dark"
perf_dip             → f"Decide: boost offer this week or accept further {metric} drop"
competitor_opened    → "Activate offer today before competitor captures nearby traffic"
dormant_with_vera    → "Re-engage this week or lapsed customers are gone permanently"
curious_ask_due      → "Surface biggest blocker using their own performance data"
regulation_change    → "Comply before deadline — non-compliance risks suspension"
cde_opportunity      → "Register before spots fill"
winback_eligible     → "Restart subscription today — every day inactive = more missed customers"
gbp_unverified       → "Verify GBP today — 2 min action, immediate visibility gain"
festival_upcoming    → f"Launch campaign now — {festival} in {days_until} days"
supply_alert         → f"Quarantine {molecule} batches immediately — patient safety"
ipl_match_today      → "Activate offer in next 2 hours — match starts tonight"
research_digest      → "Update recall protocol this week — new clinical evidence just landed"
```

**Universal payload safety net — add at END of build_message_plan(), before `return plan`:**
```python
numeric_count = sum(1 for f in plan["anchor_facts"] if re.search(r"\d", str(f)))
if numeric_count < 3:
    skip = {"trigger_id", "merchant_id", "suppression_key", "scope", "version"}
    for k, v in facts["trigger_payload"].items():
        if k in skip: continue
        if isinstance(v, (int, float)) and v not in (0, 0.0):
            plan["anchor_facts"].append(f"{k.replace('_',' ')}: {v}")
            numeric_count += 1
        elif isinstance(v, str) and len(v) > 3 and not v.startswith("http"):
            plan["anchor_facts"].append(f"{k.replace('_',' ')}: {v[:80]}")
        if numeric_count >= 4: break
```

This is the single most important block for real-judge resilience.
When the judge injects a trigger kind you've never seen, this ensures the LLM
still gets real numbers and produces a specific message instead of a 18/50 fallback.

### Step 3 — build_user_prompt()

```
CATEGORY: {slug} | TONE: {tone}
MERCHANT: {owner_name}, {locality}, {city}
CTR: {ctr_gap}
ACTIVE OFFERS: {active_offers}
LAPSED CUSTOMERS (180d+): {lapsed_customers}
TRIGGER KIND: {kind}
TRIGGER PAYLOAD: {payload verbatim}

=== ANCHOR FACTS (use ≥3 of these in your message) ===
1. {anchor_facts[0]}
2. {anchor_facts[1]}
3. {anchor_facts[2]}
...

DECISION TODAY: {decision_statement}
(Weave this into the message body as an action, not just a question)

CUSTOMER: {name}, lang={lang}, last_visit={last_visit}   ← only if present
```

### Step 4 — COMPOSER_SYSTEM

```
You are Vera, magicpin's merchant AI assistant. Write ONE WhatsApp message.

MANDATORY 3-PART STRUCTURE:
[Name] + [specific fact with number/source] → [current state RIGHT NOW] → [decision + CTA]
Every message must have all 3 parts. Missing any = max 35/50.

GOLD STANDARD (46/50):
"Dr. Meera, JIDA Oct 2026 p.14: 3-mo recall cuts caries 38% — your 124 high-risk
adults are on 6-mo protocol NOW. Switch this week? Want me to draft the patient WhatsApp?"
WHY: Dr. prefix ✓ | source+page+stat ✓ | current state "on 6-mo NOW" ✓ |
     decision "Switch this week" ✓ | specific CTA ✓ | 3 numbers (p.14, 38%, 124) ✓

HARD RULES:
1. body ≤ 320 characters — count every character
2. NO URLs
3. NO fabricated data — use ONLY anchor facts listed above
4. Start with name/Dr. prefix — NEVER "Hi", "Hello", "Vera here", "I hope"
5. ONE CTA at the end only
6. MUST include ≥3 concrete numbers/dates/sources from anchor facts
7. CURRENT STATE: include one phrase showing merchant situation RIGHT NOW
   ("CTR 3.2% while peers hit 5.8%", "0 customers since lapse", "on 6-mo protocol NOW")
8. DECISION: state ONE specific action for TODAY — not just a question
   BAD:  "Want to know more?"
   GOOD: "Reactivate today before weekend rush? Reply YES / STOP"

CTA SHAPES:
  binary:     end with "Reply YES / STOP" or "हाँ / STOP"
  open_ended: specific verb — "Want me to draft it?", "Shall I activate it?"
  none:       information only

COMPULSION LEVERS:
  loss_aversion:          quantify what's being lost right now
  effort_externalization: "I've drafted it — just say go"
  curiosity:              "want to see who?" / "want the full picture?"
  social_proof:           ONLY if peer data is in anchor facts — never fabricate

Return ONLY valid JSON:
{"body": "...", "cta": "binary|open_ended|none", "rationale": "≤60 chars"}
```

### Step 5 — validate_body()

```python
digit_groups = re.findall(r"\d+", body)
if len(digit_groups) < 2:
    return False, f"only {len(digit_groups)} number(s) — need ≥2 for specificity"

if len(body) > 320:
    return False, f"too long: {len(body)} chars"

if re.search(r"https?://", body):
    return False, "URL found — auto-reject"

BOILERPLATE = ("hi ", "hello ", "dear ", "i hope", "vera here", "i wanted")
if body.lower().startswith(BOILERPLATE):
    return False, "boilerplate opening"

# Merchant name must appear
name = (facts.get("owner_name") or facts.get("merchant_name") or "").lower()
if name and len(name) > 3:
    first = name.split()[0].rstrip(".")
    if first not in body.lower():
        return False, "merchant name missing"

return True, None
```

### Step 6 — build_grounded_fallback()

Always fires when all LLM tiers fail OR validate_body() fails twice.
Must return a real, specific message using actual facts — never empty, never generic.
Uses the universal payload scan to extract numbers from any unknown trigger kind.

***

## Known Bugs — Never Reintroduce

| Bug | Score impact | Fix |
|-----|-------------|-----|
| `_raw_digest` missing from `extract_grounding_facts()` return | regulation_change → 18/50 | Add `"_raw_digest": digest` to return dict |
| `cde_opportunity` reads `facts["digest_title"]` for event name | Webinar title wrong → 30/50 | Read `payload.get("event_name")` first |
| `curious_ask_due` has no numeric anchor_facts | Generic question → 24/50 | Add views_30d, calls_30d, ctr_gap, lapsed_customers |
| `dormant_with_vera` missing lapsed_customers + retention_6mo | "several customers" → 29/50 | Add both after ctr_gap line |
| `active_planning_intent` missing ctr_gap + peer benchmark | Single price only → 28/50 | Add ctr_gap, lapsed; set lever = "loss_aversion" |
| `category_seasonal` fallback reads `payload.get("demand_shift")` | Empty variables → 23/50 | Use `payload.get("trends", [])` list |
| `llama-3.1-70b-versatile` in MODEL_LADDER | 400 on every call, wastes budget | Remove permanently — decommissioned |
| Two Groq models consecutive in ladder | Both hit same org quota → cascading 429 | Always interleave: Groq → OR → Groq |
| `max_tokens: 600` or `max_tokens: 320` | Slow on every tier | Set to 180 exactly |
| `asyncio.sleep(1.5)` on 429 | Burns 1.5s of budget per 429 | Change to 0.3s |

***

## Scoring Rubric

5 dimensions × 10 pts = 50/pair × 30 pairs = 1500 total

| Dimension | Win | Lose |
|-----------|-----|------|
| **Decision Quality** (10) | Pick the ONE signal that matters most for this merchant+trigger+category. All 3 combined before writing. | First trigger available. Ignoring merchant state. |
| **Specificity** (10) | Real numbers, dates, sources from received context | "many customers", invented stats |
| **Category Fit** (10) | vocab_allowed, correct tone register, no vocab_taboo | Promotional to a dentist, clinical to a restaurant |
| **Merchant Fit** (10) | owner_first_name, actual locality, offers from catalog | "Hi Doctor", invented offers |
| **Engagement Compulsion** (10) | ONE binary CTA + effort externalization | Multi-ask, "let me know", no next step |

### Category Voice Rules

```python
CATEGORY_RULES = {
    "dentists":    {"taboo": ["cure","guaranteed","best dentist"],
                   "voice": "clinical peer-to-peer, Dr. prefix always"},
    "restaurants": {"taboo": ["best ever","amazing food","top restaurant"],
                   "voice": "operator-to-operator, focus on covers/footfall"},
    "salons":      {"taboo": ["cheap","discount salon","best price"],
                   "voice": "warm, aspirational, visual outcomes"},
    "gyms":        {"taboo": ["lose weight fast","guaranteed results"],
                   "voice": "motivational, data-driven, member-focused"},
    "pharmacies":  {"taboo": ["miracle","cure all"],
                   "voice": "trustworthy, utility-focused, compliance-aware"},
}
```

***

## Hard Rules (Auto-Reject or Heavy Penalty)

- `http://` or `https://` in body → auto-reject + -3 penalty
- Fabricated numbers → validation catch → fallback fires
- Re-introducing "Vera" after turn 1 → auto-reject
- Body > 320 chars → truncation = data loss = score drop
- Multiple CTAs → low compulsion score
- `"Hi"`, `"Hello"`, `"Vera here"`, `"I hope"` opener → boilerplate rejection
- Generic filler (`"increase sales"`, `"run campaign"`, `"great opportunity"`) → low specificity

***

## Test Window Flow (What the Real Judge Does)

1. **Warmup** — `/healthz` + `/metadata` checks, base context load via `/v1/context`
2. **Test window** — 60 simulated minutes, `/v1/tick` called every 5 min
3. **Adaptive injection** — fresh digest items, new metric shifts, new trigger kinds arrive mid-test
4. **Replay test** — top 10 bots face auto-replies, intent transitions, hostile/off-topic scenarios
5. **Score report** — per-message scores, logs, transcripts, judge rationale

> The universal payload scan in `build_message_plan()` is what keeps you alive
> during adaptive injection. Without it, any trigger kind the judge invents → 18/50.

***

## File Structure

```
vera-magicpin/
├── main.py                      ← FastAPI service — judge calls this
├── bot.py                       ← Identical copy of main.py — always keep in sync
├── requirements.txt
├── .env.example                 ← GROQ_API_KEY, OPENROUTER_API_KEY, SERVER_URL
│
├── test_cases_simple.py         ← Smoke test (4 cases, 30s)
├── validate_case_studies.py     ← Full validator (10 case studies, 2-3 min)
├── generate_submission.py       ← Generates submission.jsonl for 30 test cases
│
└── magicpin-ai-challenge/
    ├── dataset/
    │   ├── categories/          ← dentists, restaurants, salons, gyms, pharmacies
    │   ├── merchants_seed.json  → expanded to 50 merchants
    │   ├── customers_seed.json  → expanded to 200 customers
    │   ├── triggers_seed.json   → expanded to 100 triggers
    │   └── generate_dataset.py
    ├── expanded/
    │   └── test_pairs.json      ← 30 canonical pairs (simulator only)
    ├── examples/
    │   ├── case-studies.md      ← 10 gold standard cases
    │   └── api-call-examples.md
    └── judge_simulator.py       ← Local dry-run only — real judge uses fresh data
```

**main.py and bot.py must always be identical.**
Every change to one must be immediately replicated to the other.

***

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Add GROQ_API_KEY, OPENROUTER_API_KEY, SERVER_URL

python magicpin-ai-challenge/dataset/generate_dataset.py \
  --seed-dir magicpin-ai-challenge/dataset \
  --out magicpin-ai-challenge/expanded

uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
# Validate before shipping
python test_cases_simple.py
python validate_case_studies.py --cases 10

# Dry-run official simulator
cd magicpin-ai-challenge
python judge_simulator.py
```

***

## Debugging Checklist

| Symptom | Root cause check |
|---------|-----------------|
| Specificity < 7 | ≥3 numbers in anchor_facts? validate_body requires `len(digit_groups) >= 2`? Universal payload scan running before `return plan`? |
| Decision Quality < 7 | `decision_statement` set per kind? Injected into `build_user_prompt`? Says WHAT to decide + WHY today? |
| Category Fit < 7 | vocab_allowed present? vocab_taboo absent? Tone matches category_slug? |
| Merchant Fit < 7 | `owner_first_name` in body (not "Hi there")? Locality correct? Offers from catalog? |
| Engagement < 7 | CTA single and binary? Effort externalized ("Want me to draft it?")? No multi-asks? |
| regulation_change → 18/50 | `"_raw_digest": digest` in `extract_grounding_facts()` return dict? |
| cde_opportunity → 30/50 | `payload.get("event_name")` called BEFORE `facts["digest_title"]`? |
| curious_ask → 24/50 | views_30d, calls_30d, ctr_gap, lapsed_customers all added to anchor_facts? |
| Seasonal → 23/50 | Fallback uses `payload.get("trends", [])` list, NOT `payload.get("demand_shift")`? |
| Groq 429 cascading | Two Groq tiers consecutive? Fix: Groq → OR Gemini → Groq 8b |
| 400 on llama-3.1-70b | Remove it — decommissioned. Never re-add. |
| LLM hangs eating budget | `tier_timeout = 2.2 if groq else 3.0`? `remaining < 1.2` guard in place? |
| /healthz failing | APScheduler keep-alive running? SERVER_URL set in env? |
| Empty body returned | `build_grounded_fallback()` fires? Check LLM exhaustion logs. |

***

## Deployment Checklist (Before 02 May 2026, 11:59 PM IST)

- [ ] All 5 endpoints return correct response shapes
- [ ] `/healthz` returns `{"status":"ok","uptime_seconds":N,"contexts_loaded":N}`
- [ ] `/metadata` returns team_name, model, approach, version
- [ ] `GROQ_API_KEY` and `OPENROUTER_API_KEY` both set in production env
- [ ] `SERVER_URL` set for keep-alive pings
- [ ] `main.py` and `bot.py` are byte-for-byte identical
- [ ] `temperature: 0` on all LLM calls
- [ ] `max_tokens: 180` (not 320, not 600)
- [ ] `asyncio.sleep(0.3)` on 429 (not 1.0 or 1.5)
- [ ] `llama-3.1-70b-versatile` NOT in MODEL_LADDER
- [ ] Tier 2 of MODEL_LADDER is an OpenRouter model (not Groq)
- [ ] `validate_body()` checks `len(re.findall(r"\d+", body)) >= 2`
- [ ] Universal payload scan is last block before `return plan` in `build_message_plan()`
- [ ] `"_raw_digest": digest` present in `extract_grounding_facts()` return dict
- [ ] `cde_opportunity` reads `payload.get("event_name")` before `facts["digest_title"]`
- [ ] `curious_ask_due` adds views_30d, calls_30d, ctr_gap, lapsed_customers to anchor_facts
- [ ] Bot tested with `validate_case_studies.py --cases 10` — no crashes
- [ ] Bot stays live with zero restarts for 72h post-deadline