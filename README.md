---
title: Vera Magicpin
emoji: 🪄
colorFrom: purple
colorTo: indigo
sdk: docker
pinned: false
---

# Vera — magicpin Merchant AI Assistant

> **Challenge submission** · Vishnu · BML Munjal University 2026
> **Result:** Top 30 / 70 points · magicpin AI Challenge

---

## What is Vera?

Vera is a stateful, proactive AI engagement engine for magicpin merchants. She initiates WhatsApp-style conversations with merchants (and their customers, on behalf of merchants) by synthesizing four live context layers — category, merchant, trigger, and customer — into high-specificity, data-driven messages. Not generic nudges. Not templates.

The core thesis: **a message is only as good as the facts behind it.** Vera's entire architecture is built around one principle — decide with rules, phrase with LLM. Every message Vera sends has been pre-planned deterministically before a single token is generated.

---

## Architecture Overview

```
Judge Harness
    │
    ├── POST /v1/context     ──► In-memory context store  (4 context types, versioned)
    │
    ├── POST /v1/tick        ──► Trigger scoring
    │                            ↓
    │                        Deterministic planning layer  (extract facts, build plan)
    │                            ↓
    │                        LLM Composer  (phrase the pre-planned message)
    │                            ↓
    │                        Repair layer  (enforce numbers, urgency, CTA)
    │                            ↓
    │                        Validation  (char limit, URL check, category fit)
    │                            ↓
    │                        actions[]  (send | suppress | wait)
    │
    ├── POST /v1/reply       ──► Intent classifier → Reply composer → send/wait/end
    │
    ├── POST /v1/teardown    ──► Wipes all in-memory state
    │
    └── GET  /v1/healthz
        GET  /v1/metadata
        GET  /keep-alive
```

---

## State Management: Why In-Memory?

Vera uses three plain Python dicts for all state:

```python
contexts: dict[tuple[str, str], dict]   # (scope, id) → {version, payload, stored_at}
conversations: dict[str, dict]           # conv_id → turn history + intent state
suppression_sent: set[str]              # global dedup set for suppression keys
hostile_merchants: set[str]             # tracks merchants who replied negatively
```

**Why not Redis or SQLite?**

The judge harness runs a single isolated test session (60 minutes max, no restarts). Redis adds a network round-trip on every context lookup — that latency compounds fast when the judge sends 10 requests/second. SQLite adds disk I/O and schema management for zero benefit in a single-process, single-session context. In-memory dicts give O(1) lookup, zero serialization overhead, and are wiped cleanly by `/v1/teardown` at the end of each test run.

**Trade-off:** Dies on restart. In production, these dicts would be backed by Redis with TTL-based eviction. This was a deliberate call — optimize for the test environment, not a hypothetical production scenario that the challenge doesn't evaluate.

---

## The 4-Context Composition Framework

Every message Vera sends is the product of four context layers composed together:

| Layer | What It Contributes | Refresh Cadence |
|---|---|---|
| **Category** | Voice/tone rules, taboo words, peer benchmarks, research digest, seasonal signals | Weekly |
| **Merchant** | Name, locality, CTR, views, calls, active offers, subscription status, conversation history | Daily / real-time |
| **Trigger** | *Why NOW* — the specific event that makes this moment actionable | Per-event |
| **Customer** | Patient/customer name, last visit, language preference, slot preferences | Per-visit |

**Why four layers and not just merchant + trigger?**

Most engagement systems use merchant + trigger only. The result is messages like: *"Hi Rajesh, your CTR dropped this week. Want to boost it?"*

By adding category context, Vera knows that a dental clinic's message should reference "Dr. prefix + clinical tone + patient cohort data" and never say "cure" or "guaranteed." By adding customer context, a recall reminder becomes *"Priya's 6-month check-up is due — Slot: Tue 11am or Thu 2pm. Shall I draft the message?"* instead of a generic nudge.

The four-layer composition is what moves the specificity score from 4/10 to 9/10.

---

## The Deterministic Planning Layer (The Core Innovation)

Before any LLM call, Vera runs a fully deterministic planning pipeline:

### Step 1: `extract_grounding_facts()`

Pulls every real fact from all four context layers into a single flat dict. This includes:

- Merchant: owner name, locality, 30d views, CTR, calls, lapsed customers, active offers, subscription days remaining
- Category: peer CTR benchmark, computed CTR gap (merchant vs. peers), digest items, trend signals
- Trigger: kind, urgency score, full payload
- Customer: name, last visit date, preferred slots, services

**Why this matters:** The LLM never touches raw JSON context. It only sees pre-extracted, labelled facts. This eliminates hallucination — the LLM cannot invent a number it was never given, because numbers are injected directly into the prompt as explicit anchor facts.

### Step 2: `score_trigger()`

When multiple triggers are queued for a merchant, Vera doesn't just pick the highest urgency one. She runs a multi-factor scoring function:

- **Base score:** Urgency value × 3.0
- **Freshness bonus:** +5.0 if trigger expires within 24 hours, +2.0 within 72 hours
- **Evidence completeness:** +1.5 for having views data, +1.5 for having a benchmarkable CTR, +1.0 for active offers
- **Kind-specific bonuses:** `renewal_due` with <14 days left gets +6.0; `recall_due` with a real customer gets +4.0; `curious_ask_due` (low-evidence trigger) gets -5.0
- **Penalty:** -3.0 if trigger payload has no numeric data (message will be generic); -5.0 if no category context

**Why not just sort by urgency?**

Urgency tells you *how pressing* an event is, not *how good a message you can write about it*. A `curious_ask_due` trigger with urgency 5 and no real data will produce a worse message than a `recall_due` trigger with urgency 3 but a real patient name, slot options, and a due date. Scoring on evidence quality directly predicts message quality.

### Step 3: `build_message_plan()`

This is the "decide with rules" step. For each trigger kind, Vera deterministically decides:

- **Angle:** What specific story to tell (e.g., "Alert merchant to a -32% dip in calls this week")
- **Anchor facts:** The exact numbers/names the LLM MUST include (e.g., "30d views: 1,240", "CTR: 2.1% vs peer avg 3.8%")
- **Compulsion lever:** Which psychological lever to pull — `loss_aversion`, `social_proof`, `effort_externalization`, or `curiosity`
- **CTA shape:** `binary` (YES/STOP) or `open_ended`
- **Decision statement:** A pre-written resolution the LLM uses as its closing argument

The LLM's job is then purely phrasing — it takes this plan and writes a WhatsApp message around it. It cannot change the angle, cannot omit the anchor facts, and cannot invent new numbers.

**Why this over pure LLM composition?**

LLMs are excellent at phrasing. They are unreliable at deciding which facts matter, which lever to pull, and what angle maximises engagement for a specific merchant category. Separating decision from phrasing gives you consistency, auditability, and resistance to hallucination — all critical in a scoring environment where every fabricated number is a penalty.

---

## The LLM Layer

### Model Ladder (8 Tiers)

Vera uses a tiered fallback system across four providers:

```python
MODEL_LADDER = [
    ("mistral",    "mistral-small-latest"),       # Tier 1: 2.25M TPM, 5 RPS, best throughput
    ("groq",       "llama-3.3-70b-versatile"),    # Tier 2: fast, high quality, no RPS gap
    ("mistral",    "mistral-medium-2505"),         # Tier 3: separate quota pool, 60K TPM
    ("groq",       "llama-3.1-8b-instant"),        # Tier 4: 14,400 RPD, ultra-fast fallback
    ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),  # Tier 5: free tier
    ("openrouter", "google/gemma-4-31b-it:free"), # Tier 6: free tier diversity
    ("openrouter", "openai/gpt-oss-120b:free"),   # Tier 7: free tier last resort
    ("openai",     "gpt-4o-mini"),                 # Tier 8: paid, absolute last resort
]
```

**Why Mistral first and not Gemini (which was Tier 1 in v1)?**

Gemini 2.5 Flash was the original Tier 1. Under concurrent judge load (10 req/sec), it hit rate limits within the first few test scenarios. Mistral Small has a 2.25M TPM quota with 5 RPS — enough to absorb burst load without degrading to fallbacks mid-test. Mistral also enforces a 1-RPS hard limit, so Vera includes a `_mistral_last_call` global timestamp and sleeps 1.05s between calls to stay compliant.

**Why Groq at Tier 2 and not Tier 1?**

Groq is extremely fast (sub-500ms) but has tighter per-model RPD limits. Using it as Tier 2 means it absorbs overflow from Mistral rather than burning its quota on every single request. This preserves Groq quota for the high-concurrency scenarios where Mistral is sleeping through its 1.05s window.

**Why eight tiers and not two or three?**

The judge runs 30+ test pairs in sequence, sometimes with concurrency. Any single provider will hit a rate limit at scale. Having eight tiers means Vera has never returned an empty body in testing — there is always a fallback available. The cost of having extra tiers is near-zero (they only activate on failure). The cost of not having them is a 0-point response.

### Concurrency Control: `LLM_SEMAPHORE`

```python
LLM_SEMAPHORE = asyncio.Semaphore(1)
```

All LLM HTTP calls are serialized through a single semaphore. This is the single most counterintuitive design decision in the system — and the most important one.

**Why serialize LLM calls when FastAPI is async?**

Mistral has a 1 RPS hard limit. If the judge sends 10 `/v1/tick` requests simultaneously, without serialization, all 10 would try to call Mistral concurrently → 9 get 429s → all 9 fall through to Groq → Groq burns its hourly RPD limit in 2 minutes → cascade to OpenRouter free tiers → quality degrades for the rest of the test.

Serialization ensures that only one LLM call is in-flight at any time. The plan-building, validation, and repair steps still run fully concurrently — only the HTTP call is gated. In practice, this adds ~200ms of queuing latency in the worst case, which is far preferable to cascading 429s.

### Temperature: Always 0

Every LLM call uses `temperature: 0`. This is required by the challenge spec for determinism, but it also has a practical benefit: deterministic outputs make debugging much easier. When a message is wrong, the problem is always in the plan or the system prompt — not in LLM randomness.

---

## The Repair Layer: `repair_body()`

Even with a perfect plan and a good LLM response, the raw output can fail judge-visible checks. The repair layer runs deterministically after the LLM returns and before validation:

1. **Name enforcement:** Prepends `Dr.` for dentists if the owner name doesn't already have it. Prepends the owner name if it's missing from the first 80 characters.
2. **Locality injection:** If the merchant's locality isn't mentioned in the body, injects it after the first clause.
3. **Category term enforcement:** If no category-relevant term appears (e.g., "patients", "covers", "bookings"), appends a category-specific repair phrase.
4. **Urgency enforcement:** If no urgency term appears ("today", "now", "this week", etc.), appends "today." to the end.
5. **Number grounding:** If fewer than 3 numbers appear in the message, injects available metrics (views, calls, lapsed customers, CTR) until the threshold is met.
6. **CTA enforcement:** Removes weak one-word CTAs ("reply yes", "go") and appends the required `Reply YES / STOP` binary CTA.
7. **Length enforcement:** Truncates to 320 characters if over-limit, preserving the CTA suffix.

**Why a repair layer instead of just better prompting?**

Prompting for 5 simultaneous constraints (name, locality, category terms, urgency, 3 numbers, CTA, length) across 8 different models at temperature 0 produces inconsistent results. Some models follow all constraints; others miss one or two. The repair layer is a deterministic safety net — it guarantees minimum compliance regardless of which model responded. The judge scores on what's in the final message, not on prompt cleverness.

---

## Category Intelligence

Vera handles five merchant categories, each with its own rules:

| Category | Voice | Taboo Words | Required Terms |
|---|---|---|---|
| Dentists | Clinical, peer-to-peer, "Dr." prefix | "cure", "guaranteed", "best dentist" | "patient", "protocol", "recall", "clinical" |
| Restaurants | Operator-to-operator, footfall-focused | "best ever", "amazing food" | "covers", "footfall", "orders", "delivery" |
| Salons | Warm, aspirational, visual outcomes | "cheap", "discount salon" | "bookings", "bridal", "walk-ins", "stylist" |
| Gyms | Motivational, data-driven, member-focused | "lose weight fast", "guaranteed results" | "members", "retention", "trial", "membership" |
| Pharmacies | Trustworthy, utility-focused, compliance-aware | "miracle", "cure all" | "refills", "stock", "batch", "compliance" |

Taboos are enforced in the system prompt. Required terms are enforced by the repair layer. This two-layer approach means even if the LLM slips on tone (which happens at Tier 4+), the repair layer catches missing category signals.

---

## Trigger Handling (20 Trigger Kinds)

Vera handles 20 distinct trigger kinds, each with a pre-defined plan structure:

| Trigger Kind | Angle | Compulsion Lever |
|---|---|---|
| `research_digest` | Share new clinical/industry finding | Effort externalization |
| `perf_dip` | Alert to metric decline | Loss aversion |
| `perf_spike` | Capitalize on momentum | Social proof |
| `renewal_due` | Subscription expiry warning | Loss aversion |
| `recall_due` | Patient recall reminder | Effort externalization |
| `festival_upcoming` | Festival campaign hook | Social proof |
| `review_theme_emerged` | Coach on emerging review pattern | Curiosity |
| `ipl_match_today` | IPL match traffic opportunity | Loss aversion |
| `competitor_opened` | Protect position against new rival | Loss aversion |
| `winback_eligible` | Lapsed subscription re-engagement | Loss aversion |
| `curious_ask_due` | Performance gap snapshot | Loss aversion |
| `wedding_package_followup` | Bridal package lead follow-up | Effort externalization |
| `dormant_with_vera` | Re-engage silent merchant | Loss aversion |
| `regulation_change` | Compliance deadline alert | Loss aversion |
| `milestone_reached` | Celebrate near-milestone moment | Social proof |
| `active_planning_intent` | Deliver on merchant's stated intent | Loss aversion |
| `customer_lapsed_hard/soft` | Customer winback campaign | Loss aversion |
| `trial_followup` | Convert trial to membership | Effort externalization |
| `supply_alert` | Urgent stock recall warning | Loss aversion |
| `chronic_refill_due` | Chronic patient refill reminder | Effort externalization |
| `category_seasonal` | Seasonal demand shift | Social proof |
| `gbp_unverified` | Google Business Profile fix | Loss aversion |

Unknown trigger kinds are not suppressed. They receive a score floor of 2.0 and fall through to a universal payload scan that extracts any numeric values from the trigger payload for grounding.

---

## Conversation State Machine

When a merchant replies, Vera classifies their intent and responds accordingly:

```
SENT  →  [merchant replies]
              ↓
        Intent classification:
        - "committed" (yes, let's do it, okay, confirmed)
        - "hostile"   (stop, no, not interested, unsubscribe)
        - "neutral"   (question, partial interest)
              ↓
        COMMITTED  →  Deliver the promised next step (≤160 chars, ACTION words)
        HOSTILE    →  Respect and close (mark merchant hostile, suppress future)
        NEUTRAL    →  Acknowledge + ONE specific binary follow-up question
```

Hostile merchants are added to `hostile_merchants` set. All subsequent ticks for hostile merchants return `suppress` actions. This prevents Vera from re-engaging merchants who have opted out — a critical compliance requirement and a real engagement quality signal.

---

## Keep-Alive System

Vera is deployed on Hugging Face Spaces, which hibernates inactive containers after ~15 minutes. The keep-alive scheduler pings `/v1/healthz` every 10 minutes via local loopback (`127.0.0.1:7860`) to bypass HuggingFace's public rate limiter.

**Why loopback and not the public URL?**

HuggingFace rate-limits external pings to prevent abuse. Pinging the public URL would count against the rate limit and potentially trigger a 429 on the health endpoint itself. Loopback bypasses the public rate limiter entirely because the request never leaves the container.

---

## Scoring Strategy (5 Dimensions)

The challenge scores each message on five dimensions (10 pts each):

| Dimension | How Vera Maximizes It |
|---|---|
| **Specificity** | Injects CTR numbers, 30d views, lapsed customer counts, trial N, source citations — all from real context data |
| **Category fit** | Taboo enforcement in system prompt + required term enforcement in repair layer |
| **Merchant fit** | Owner first name, locality, active offers, and subscription status all injected via anchor facts |
| **Trigger relevance** | Kind-specific angle and anchor facts built deterministically per trigger kind |
| **Engagement compulsion** | Effort externalization ("I drafted it for you"), loss aversion framing, binary CTA every time |

**Anti-patterns actively blocked:**
- URLs anywhere in the body (-3 penalty from judge) — validated and stripped before output
- Body > 320 chars — truncated in repair layer with CTA preserved
- Re-introducing Vera after Turn 1 — turn counter passed to LLM prompt
- Generic messages with no numbers — repair layer enforces ≥3 numeric values

---

## API Endpoints Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root health check |
| `GET` | `/keep-alive` | Keep-alive + uptime |
| `GET` | `/v1/healthz` | Judge health check |
| `GET` | `/v1/metadata` | Service metadata |
| `POST` | `/v1/context` | Push context (category/merchant/trigger/customer) |
| `POST` | `/v1/tick` | Run engagement decision for a merchant |
| `POST` | `/v1/reply` | Handle merchant reply in an active conversation |
| `POST` | `/v1/teardown` | Wipe all in-memory state |

**Idempotency:** Context pushes with a stale version number return HTTP 409. This prevents the judge from accidentally overwriting newer context with an older version in out-of-order delivery scenarios.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | Primary gateway for Tiers 5–7 |
| `MISTRAL_API_KEY` | Recommended | Tier 1 and 3 — highest throughput |
| `GROQ_API_KEY` | Recommended | Tier 2 and 4 — fastest response |
| `OPENAI_API_KEY` | Optional | Tier 8 — paid last resort |
| `GEMINI_API_KEY` | Optional | Alternative provider (not in current ladder) |
| `ENABLE_PRELOAD` | Optional | Set `true` to preload contexts from disk on startup |
| `DATASET_DIR` | Optional | Path to dataset directory for preload |

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env → add your API keys

# 3. Run
uvicorn main:app --host 0.0.0.0 --port 7860

# 4. Test with the judge simulator
export BOT_URL=http://localhost:7860
python judge_simulator.py --scenario warmup
python judge_simulator.py --scenario all
```

---

## File Structure

```
vera-magicpin/
├── main.py              ← Full service: API, state, planning, LLM, compose, reply
├── requirements.txt
├── .env.example
└── README.md
```

All logic lives in `main.py`. This is intentional — the challenge evaluates a single deployable service. For a production system, this would be split into: `router/`, `planner/`, `composer/`, `validators/`, `state/`.

---

## Key Design Tradeoffs

| Decision | Why | What's Lost |
|---|---|---|
| In-memory state only | Zero latency, simple, correct for test scope | Dies on restart — Redis needed for production |
| Single `main.py` file | Fast to ship, debug, and reason about | Not modular for a team; hard to unit test in isolation |
| Deterministic planning before LLM | Eliminates hallucination, enforces scoring requirements | Requires maintaining a plan for each trigger kind manually |
| `Semaphore(1)` for LLM calls | Prevents cascading 429s under concurrent judge load | Adds ~200ms queuing latency in burst scenarios |
| Temperature 0 everywhere | Deterministic, judge-friendly | No creative variation — same input always same output |
| Repair layer after LLM | Guarantees minimum compliance across all 8 models | Adds 1-2ms per response; can produce slightly mechanical endings |
| 8-tier model ladder | Never returns empty body; survives any single provider outage | Tier 8 (GPT-4o-mini) costs money — but activates extremely rarely |
| Loopback keep-alive | Bypasses HF public rate limiter | Only works inside the container — not useful outside HF Spaces |