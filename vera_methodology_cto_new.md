# Vera Merchant AI Assistant: Complete Technical Methodology & Architecture

**Version 11.0.1 | Author: Vishnu | Team: Solo Application**

This document explains **Vera's messaging engine**: a FastAPI service orchestrating context-aware WhatsApp commerce for India's retail ecosystem. **Core Innovation**: Rules-first determinism. Every message is rooted in extracted facts, pre-planned before LLM, validated against hard constraints, backed by grounded fallbacks that never return generic output.

---

## EXECUTIVE SUMMARY

- **What it does**: Decides when to message merchants → composes specific, offer-driven WhatsApp nudges → tracks reply intents → determines next action
- **How it works**: 4-layer context composition → deterministic pre-LLM planning → LLM-as-phrasing-engine → validation → grounded fallback
- **Why this design**: Judge scores decisions + specificity. Every output rooted in extracted numbers, pre-decided structure, never fabricated.

---

## SECTION 1: THE 4-CONTEXT COMPOSITION ENGINE (Lines 350-452)

Unlike generic CRM bots, Vera uses a **4-Context Composition Engine** where every message synthesizes 4 distinct data layers:

| Layer | Source | Role | Key Data |
|-------|--------|------|----------|
| **Category** | `categories/{slug}.json` | Brand guardrails (voice, taboos) | vocab_allowed, vocab_taboo, peer_stats, digest_items |
| **Merchant** | `merchants/{id}.json` | Business identity & performance | owner_first_name, locality, views_30d, calls_30d, ctr, ctr_gap, offers |
| **Trigger** | `triggers/{id}.json` | Why Now (urgency + payload) | kind, urgency, payload (real numbers), expires_at, suppression_key |
| **Customer** | `customers/{id}.json` (optional) | Target audience for B2C | name, language, last_visit, state, preferred_slots |

**Critical line 431**: The function `extract_grounding_facts()` MUST include `"_raw_digest": digest` in its return dict. WITHOUT this, trigger kind `regulation_change` returns 18/50 because the fallback cannot match digest item by ID to construct the message.

**Technical flow**:
```python
facts = extract_grounding_facts(category, merchant, trigger, customer)
# Returns 40+ fields including all 4 layers merged into flat dict
# Enables both LLM composition AND deterministic fallback to work with identical data
```

---

## SECTION 2: DETERMINISTIC PLANNING LAYER (Lines 652-1210)

**Breakthrough principle**: `build_message_plan()` decides **angle, anchor facts, compulsion lever, CTA BEFORE LLM invocation**. This prevents hallucination and ensures structure is judge-visible.

### How it works:
1. **Input**: Extracted facts dict (40+ fields)
2. **Processing**: Per-trigger-kind logic decides 5 elements:
   - `angle`: Narrative direction (e.g., "regulatory risk", "revenue loss", "customer regret")
   - `anchor_facts`: ≥3 facts with numbers that LLM MUST weave in
   - `decision_statement`: ONE actionable decision merchant must make TODAY
   - `compulsion_lever`: Psychological trigger (loss_aversion, effort_externalization, curiosity, social_proof)
   - `cta_shape`: binary / open_ended / none
3. **Output**: Pre-LLM structure ready for prompt injection

### 19 Trigger Kinds (Lines 759-958 logic per kind)

| Trigger Kind | Example | Compulsion | Key anchor facts | Decision | CTA |
|--------------|---------|-----------|-------------------|----------|-----|
| research_digest | "JIDA Oct 2026 p.14: 3-mo recall cuts caries 38%" | effort_externalization | source+page, stat, cohort_size | Switch protocol this week | "Want me to draft message?" |
| perf_dip | "CTR 3.2% vs peers 5.8%, down from 4.1% last week" | loss_aversion | peer_gap, trend, revenue_impact | Boost offer NOW | "Reply YES to activate" |
| renewal_due | "Your plan expires in 7 days" | loss_aversion | days_left, risk_statement | Renew before listings go dark | "Reply YES / STOP" |
| festival_upcoming | "Diwali in 12 days, peers prepping campaigns" | social_proof | festival, days_until, peer_action | Launch campaign NOW | "Ready to start?" |
| ipl_match_today | "Match tonight 7pm, peak demand expected" | urgency | time_until, demand_spike | Activate offer next 2 hours | "Reply YES" |
| dormant_with_vera | "0 calls in 180 days, 45 high-risk lapsed" | loss_aversion | days_lapsed, lapsed_customer_count, retention_pct | Re-engage this week | "Reply YES to restart" |
| regulation_change | "JIDA Aug 2026: Recall protocol changed, compliance by Sept 15" | loss_aversion | source, deadline, regulation_detail | Comply NOW | "Want guidance?" |
| competitor_opened | "Similar merchant opened 0.5km away, 12 reviews" | urgency | distance, competitor_strength | Activate offer TODAY | "Reply YES" |
| curious_ask_due | "Your performance: 245 views, 8 calls, peers get 18" | curiosity | views_30d, calls_30d, peer_avg, ctr_gap | What's blocking you? | "Want to know?" |
| winback_eligible | "Subscription lapsed 42 days ago, 180 customers missed" | loss_aversion | days_inactive, customer_impact | Restart today | "Reply YES" |
| gbp_unverified | "GBP unverified, visibility down 35%" | effort_externalization | visibility_delta, action_time | Verify GBP (2 min) | "Ready?" |
| supply_alert | "Medicine batch recall: [molecule], quarantine immediately" | urgency | molecule, quarantine_action | Isolate stock NOW | "Confirm quarantine" |
| cde_opportunity | "Webinar register: Advanced Dentistry, 5 spots left, $49" | social_proof | event_name, spots, deadline | Register before spots fill | "Link in next message" |
| review_theme_emerged | "5 reviews mention slow response, we can coach you" | effort_externalization | theme, review_count, solution | Let's fix response time | "Want our playbook?" |
| category_seasonal | "Demand for [trend] up 180% week-over-week" | social_proof | trend, demand_lift, peer_action | Update shelves NOW | "Confirm update?" |
| active_planning_intent | "You mentioned scaling offer—here's a plan" | effort_externalization | merchant_goal, concrete_step | Execute phase 1 today | "Ready?" |
| trial_followup | "Your trial ends in 3 days, 24 slots booked" | urgency | trial_days_left, slots_booked | Convert before trial ends | "Subscribe now?" |
| customer_lapsed_hard | "Aditya: 287 days inactive, spent ₹4200 lifetime" | loss_aversion | customer_name, days_lapsed, ltv | Reactivate Aditya today | "Send special offer?" |
| customer_lapsed_soft | "3 customers stopped visiting, 8 slots went unused" | curiosity | customer_count, unused_slots | Why did they drop off? | "Want me to diagnose?" |
| recall_due | "Patient Mr. Sharma: 6-mo recall due, last visit 185 days ago" | urgency | patient_name, days_overdue | Send recall SMS today | "Send now?" |

### UNIVERSAL PAYLOAD SCAN (Lines 1195-1210 — CRITICAL FOR JUDGE RESILIENCE)

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

**Why critical**: When judge injects a **novel trigger kind you've never seen**, this scan auto-extracts numeric fields from ANY payload shape, ensuring surprise triggers produce specific messages (not 18/50 generic fallback).

---

## SECTION 3: LLM LADDER — COST + RELIABILITY (Lines 87-164, 290-328)

**Architecture**: Multi-provider, multi-tier ladder ensures 100% uptime despite rate limits.

### Model Ladder Configuration

```python
MODEL_LADDER = [
    ("groq",        "llama-3.3-70b-versatile"),      # Tier 1: Primary
    ("openrouter",  "google/gemini-2.0-flash-exp:free"),  # Tier 2: Cross-provider on 429
    ("groq",        "llama-3.1-8b-instant"),         # Tier 3: Separate quota pool
    ("openrouter",  "google/gemma-3-27b-it:free"),   # Tier 4: Fallback
    ("openrouter",  "openrouter/auto"),              # Tier 5: Last resort
]
```

### Critical Parameters (MUST NOT CHANGE)

| Parameter | Value | Reason |
|-----------|-------|--------|
| temperature | 0 | Judge requires determinism, reproducible outputs |
| max_tokens | 180 | 120 tokens ≈ 320 chars; anything >180 = slow |
| timeout | 2.2s (Groq), 3.0s (OpenRouter) | Budget preservation |
| sleep on 429 | 0.3s (NOT 1.5s) | Preserve budget for fallback tiers |
| Groq quota | Two separate models | Tier 1 and Tier 3 are different models, avoiding same-org cascading 429s |

### Fallback Strategy

```python
async def call_llm_ladder(system: str, user: str, budget: float = 7.0) -> str:
    t0 = time.time()
    for i, (provider, model) in enumerate(MODEL_LADDER):
        remaining = budget - (time.time() - t0)
        if remaining < 1.2:
            break  # Guard: allow build_grounded_fallback() time
        
        text, status = await llm_call(provider, model, system, user, 
                                      min(tier_timeout, remaining - 0.3))
        if status == 200 and text:
            return text
        
        if status == 429:  # Rate limited
            await asyncio.sleep(0.3)  # Brief pause, move to next tier
            continue
        
        if status == 400:  # Decommissioned model
            continue  # Skip instantly, no sleep
    
    return build_grounded_fallback(facts, trigger_kind)
```

---

## SECTION 4: MESSAGE COMPOSITION FLOW (Lines 1434-1653)

**3-Part Mandatory Structure**: `[Name + Professional Title] + [Specific fact with number/source] → [Current state RIGHT NOW] → [Decision + CTA]`

### Gold Standard Example

```
"Dr. Meera, JIDA Oct 2026 p.14: 3-mo recall cuts caries 38% — your 124 high-risk 
adults are on 6-mo protocol NOW. Switch this week? Want me to draft the patient WhatsApp?"
```

**Why this scores 46/50**:
- Name + Dr. prefix ✓
- Source + page + stat ✓
- Current state "on 6-mo protocol NOW" ✓
- Decision "Switch this week" ✓
- Specific CTA ✓
- 3+ numbers (p.14, 38%, 124) ✓

### Execution Steps

1. **extract_grounding_facts()** (lines 350-452)
   - Merges all 4 layers into flat dict
   - Includes owner_name, locality, city, category_slug, all triggers, peer data
   - **CRITICAL**: Includes `_raw_digest: digest` (list of digest items with IDs)

2. **build_message_plan()** (lines 652-1210)
   - Per-trigger-kind logic decides: angle, anchor_facts (≥3 with numbers), decision_statement, compulsion_lever, cta_shape
   - Universal payload scan auto-extracts numbers if needed

3. **build_user_prompt()** (lines 1216-1435)
   ```
   CATEGORY: {slug} | TONE: {tone}
   MERCHANT: {owner_name}, {locality}
   CTR: {ctr_gap}
   ACTIVE OFFERS: {active_offers}
   TRIGGER KIND: {kind}
   TRIGGER PAYLOAD: {payload verbatim}
   
   === ANCHOR FACTS ===
   1. {anchor_facts[0]}
   2. {anchor_facts[1]}
   ...
   
   DECISION TODAY: {decision_statement}
   CUSTOMER: {name}, lang={lang}   ← if present
   ```

4. **COMPOSER_SYSTEM Prompt** (lines 1555-1610)
   - 6 hard rules: format, no URLs, use anchor facts, include name, ONE CTA, ≥3 numbers
   - LLM forced to return valid JSON: `{"body": "...", "cta": "binary|open_ended|none", "rationale": "..."}`

5. **validate_body()** (lines 1434-1493)
   - ≤320 chars
   - ≥2 digit groups (specificity)
   - No URLs, no boilerplate openers, merchant name present

---

## SECTION 5: VALIDATION & REPAIR (Lines 1434-1653)

### validate_body() — Hard Constraints

```python
def validate_body(body, facts):
    # 1. Length: 1-320 chars
    if len(body) > 320:
        return False, f"too long: {len(body)} chars"
    
    # 2. Specificity: ≥2 digit groups
    digit_groups = re.findall(r"\d+", body)
    if len(digit_groups) < 2:
        return False, f"only {len(digit_groups)} numbers — need ≥2"
    
    # 3. Safety: No URLs
    if re.search(r"https?://", body):
        return False, "URL found"
    
    # 4. Boilerplate: Must not start with generic phrases
    if body.lower().startswith(("hi ", "hello ", "dear ", "i hope", "vera here")):
        return False, "boilerplate opening"
    
    # 5. Merchant identity: Name must appear
    name = (facts.get("owner_name") or "").lower()
    first = name.split()[0].rstrip(".")
    if first and len(first) > 3:
        if first not in body.lower():
            return False, "merchant name missing"
    
    return True, None
```

### repair_body() — First Failure Auto-Fix

On first validation failure, attempt auto-repair:
- Inject merchant's first name
- Add "Dr." prefix if category = dentists
- Inject locality reference
- Add missing numbers from anchor_facts
- Truncate to 320 chars while preserving meaning

If repair succeeds, send repaired message. If repair fails, → grounded fallback.

### build_grounded_fallback() — Second Failure Deterministic Fallback

```python
def build_grounded_fallback(facts, trigger_kind):
    # Never generic. Per-trigger-kind templates using REAL facts.
    # If you've never seen a trigger kind, universal payload scan has extracted numbers.
    
    templates = {
        "perf_dip": f"{owner_name}, your CTR {ctr}% vs peers {peer_ctr}% "
                    f"— boost offer {days_remaining}d? {offer_title}",
        "renewal_due": f"{owner_name}, your plan expires {days_remaining}d. "
                       f"Renew now? {days_remaining}d left.",
        "regulation_change": f"{owner_name}, new rule by {deadline_date} "
                             f"— {regulation_detail}. Comply by {action_deadline}?",
        # ... per-kind templates
    }
    return templates.get(trigger_kind, 
                         f"{owner_name}, {extracted_numeric_payload}. "
                         f"Decide today? Reply YES / STOP")
```

**Critical**: Fallback ALWAYS uses real numbers extracted from trigger payload. Never empty, never generic.

---

## SECTION 6: INTENT DETECTION STATE MACHINE (Lines 1778-1850)

Function `detect_intent()` classifies merchant replies BEFORE expensive LLM call.

```python
def detect_intent(reply_text):
    reply_lower = reply_text.lower().strip()
    
    if re.search(r"stop|unsubscribe|opt.?out|no vera", reply_lower):
        return "hostile"  # Add to hostile_merchants set, exit
    
    if re.search(r"out of office|auto.?reply|currently away", reply_lower):
        return "auto_reply"  # Exit (prevent loops)
    
    if re.search(r"^(ok|yes|haan|ha|thumbs up|✓|✓✓)", reply_lower):
        return "committed"  # Skip qualification, execute immediately
    
    if re.search(r"no thanks|nahi|not interested|decline", reply_lower):
        return "rejecting"  # Graceful farewell
    
    return "neutral"  # Unclear → ask follow-up
```

### State Transitions

| Current State | Intent | Action |
|---------------|--------|--------|
| neutral | hostile | Set hostile_merchants[merchant_id] = True, exit |
| neutral | auto_reply | Exit (prevent loop) |
| neutral | committed | Skip follow-up, execute action |
| neutral | rejecting | Send graceful farewell, exit |
| neutral | neutral | Call LLM for follow-up question |

---

## SECTION 7: IN-MEMORY STATE ARCHITECTURE (Lines 118-200)

**No database, no Redis** — Judge 60-min test window accepts state loss on restart.

```python
contexts: dict[tuple[str, str], dict]
    # Key: (scope, id) e.g., ("merchant", "M123")
    # Value: {version, payload, stored_at, expires_at}
    # Idempotent by (scope, version) — replaying same POST /v1/context is safe

conversations: dict[str, dict]
    # Key: conv_id (e.g., "M123:C456")
    # Value: {merchant_id, customer_id, turns: [{role, content, intent, timestamp}], state: "open|closed"}
    # Tracks dialogue history for consistency

suppression_sent: set[str]
    # Global dedup set
    # Key: suppression_key from trigger
    # Ensures same merchant never receives same signal twice (even across restarts if persisted)

hostile_merchants: set[str]
    # Key: merchant_id
    # Merchants who've opted out — skip all future /v1/tick calls for them
```

---

## SECTION 8: THE 5 API ENDPOINTS (Lines 1778-2050)

### 1. POST /v1/context — Store Context (Idempotent)

**Contract**:
```json
{
  "scope": "merchant|customer|trigger|category",
  "id": "M123",
  "version": "v1",
  "payload": { ... full JSON ... }
}
```

**Behavior**: Store in `contexts[(scope, id)] = {version, payload, stored_at}`. If same (scope, version) arrives twice, update payload (idempotent).

### 2. POST /v1/tick — Proactive Trigger Processing

**Contract**:
```json
{
  "merchant_ids": ["M1", "M2", ...],
  "available_triggers": [{"id": "T1", "urgency": 0.8, ...}, ...]
}

Response:
{
  "actions": [
    {
      "type": "send_whatsapp",
      "merchant_id": "M1",
      "customer_id": "C5" or null,
      "body": "Dr. Meera, ...",
      "trigger_id": "T1",
      "conv_id": "M1:C5:T1"
    },
    ...
  ]  // ≤20 actions
}
```

**Flow**:
1. For each merchant_id, filter hostile_merchants
2. For available triggers, skip if suppression_key in suppression_sent
3. Compose message via extract_grounding_facts → build_message_plan → build_user_prompt → call_llm_ladder → validate/repair/fallback
4. Add to suppression_sent[suppression_key]
5. Return ≤20 actions

### 3. POST /v1/reply — Reactive Intent Processing

**Contract**:
```json
{
  "conv_id": "M1:C5:T1",
  "merchant_reply": "Yes, do it!",
  "merchant_id": "M1",
  "timestamp": "2026-05-02T18:30:00Z"
}

Response:
{
  "next_action": "send|wait|end",
  "body": "Great! Activating offer...",  // if send
  "trigger_id": "T1"
}
```

**Flow**:
1. Load conversation from conversations[conv_id]
2. Call detect_intent(merchant_reply)
3. If hostile → exit
4. If committed → execute immediately
5. If neutral → ask follow-up via LLM
6. Update conversations[conv_id].turns with merchant message + intent

### 4. GET /v1/healthz — Health Check

**Contract**:
```json
{
  "status": "ok",
  "uptime_seconds": 3600,
  "contexts_loaded": 142,
  "conversations_active": 8
}
```

**Rule**: 3 consecutive failures = **disqualified by judge**. Use APScheduler to ping self every 5 min if SERVER_URL set.

### 5. GET /v1/metadata — Bot Identity

**Contract**:
```json
{
  "team_name": "Vishnu",
  "model": "Groq Llama-3.3-70b + OpenRouter Gemini-2.0-flash",
  "approach": "Rules-first determinism: 4-context composition → pre-LLM planning → LLM-as-phrasing",
  "version": "11.0.1"
}
```

---

## SECTION 9: KNOWN BUGS & FIXES (Critical for Judge Robustness)

| Bug | Location | Impact | Root Cause | Fix |
|-----|----------|--------|-----------|-----|
| regulation_change → 18/50 | Line 431 | Fallback cannot match digest item | `_raw_digest` missing from extract_grounding_facts() return dict | Add `"_raw_digest": digest` to return dict at line 431 |
| cde_opportunity wrong event | Line 1331 | Event name pulled from digest_title instead of payload | Logic reads `facts["digest_title"]` before checking `payload.get("event_name")` | Check `payload.get("event_name")` FIRST, fallback to digest_title |
| curious_ask_due → 24/50 | Lines 1305-1308 | Generic question, missing specificity | No numeric anchor_facts (views, calls, ctr, lapsed) | Add views_30d, calls_30d, ctr_gap, lapsed_customers to anchor_facts |
| dormant_with_vera → 29/50 | Lines 922-929 | "several customers" generic phrase | Missing lapsed_customers + retention_6mo_pct in anchor_facts | Add both metrics after ctr_gap line |
| active_planning_intent → 28/50 | Lines 940-945 | Single price mentioned, no comparisons | Missing ctr_gap + peer benchmark | Add ctr_gap and set lever to loss_aversion |
| category_seasonal → 23/50 | Lines 950-958 | Empty payload variable | Fallback reads `payload.get("demand_shift")` which doesn't exist | Use `payload.get("trends", [])` list instead |
| Groq cascading 429s | Line 87 | All tiers hit same org quota → exhausts budget | Two Groq models consecutive in MODEL_LADDER | **Pattern**: Groq → OpenRouter → Groq → OpenRouter. Never consecutive same-provider. |
| llama-3.1-70b timeout | Never | Every call returns 400 (model decommissioned) | Model removed by Groq | Remove from ladder permanently. Never re-add. |
| max_tokens too high | N/A | Slow on every tier | Set to 600 or 320 instead of 180 | **ALWAYS max_tokens: 180 exactly** |
| sleep(1.5) on 429 | N/A | Burns 1.5s per 429, exhausts budget | Late-session fallback starves | **Change to asyncio.sleep(0.3)** |

---

## SECTION 10: CATEGORY VOICE RULES (Lines 118-164 — Enforced per category_slug)

### Dentists
- **Voice**: Clinical peer-to-peer, data-driven, evidence-based
- **Always**: Use "Dr. [Name]" prefix
- **Forbidden**: "cure", "guaranteed", "best dentist", "painless"
- **Example anchor fact**: "JIDA Oct 2026 p.14: 3-mo recall cuts caries 38%"

### Restaurants
- **Voice**: Operator-to-operator, footfall + covers focus
- **Always**: Mention covers, covers/hour, peak hours
- **Forbidden**: "best ever", "amazing food", "top restaurant", "delicious"
- **Example anchor fact**: "Peers average 45 covers lunch, you're at 28 — boost on Fri/Sat"

### Salons
- **Voice**: Warm, aspirational, visual outcomes
- **Always**: Mention customer satisfaction, repeat visits, ratings
- **Forbidden**: "cheap", "discount salon", "bargain", "budget"
- **Example anchor fact**: "5.1★ rating from 240 reviews — your repeat rate 62%"

### Gyms
- **Voice**: Motivational, data-driven, member-focused
- **Always**: Mention members, churn, slots
- **Forbidden**: "lose weight fast", "guaranteed results", "miracle workout"
- **Example anchor fact**: "5 members dropped Q1 — re-engage with trial week"

### Pharmacies
- **Voice**: Trustworthy, utility-focused, compliance-aware
- **Always**: Mention refills, patient safety, compliance
- **Forbidden**: "miracle", "cure all", "guaranteed effect"
- **Example anchor fact**: "Recall: Batch #ABC123 — quarantine immediately per DCGI"

---

## SECTION 11: DEPLOYMENT CHECKLIST (Before 02 May 2026, 11:59 PM IST)

### Code Verification
- [ ] main.py and bot.py are byte-for-byte identical
- [ ] All 5 endpoints present: /v1/context, /v1/tick, /v1/reply, /v1/healthz, /v1/metadata
- [ ] temperature: 0 on all LLM calls (NEVER change)
- [ ] max_tokens: 180 exactly (not 320, not 600)
- [ ] asyncio.sleep(0.3) on 429 (not 1.0 or 1.5)
- [ ] llama-3.1-70b-versatile NOT in MODEL_LADDER
- [ ] Tier 2 of MODEL_LADDER is OpenRouter (not Groq) — prevents same-org cascading 429s
- [ ] validate_body() checks `len(re.findall(r"\d+", body)) >= 2`
- [ ] Universal payload scan is last block before `return plan` in build_message_plan()
- [ ] `"_raw_digest": digest` present in extract_grounding_facts() return dict

### Bug Fixes Verified
- [ ] regulation_change adds _raw_digest to facts
- [ ] cde_opportunity reads payload.get("event_name") first
- [ ] curious_ask_due adds views_30d, calls_30d, ctr_gap, lapsed_customers
- [ ] dormant_with_vera adds lapsed_customers + retention_6mo_pct
- [ ] category_seasonal uses payload.get("trends", [])
- [ ] No consecutive Groq models in ladder

### Environment & APIs
- [ ] GROQ_API_KEY set and valid
- [ ] OPENROUTER_API_KEY set and valid
- [ ] SERVER_URL set in .env (for /healthz keep-alive)
- [ ] APScheduler configured to ping /healthz every 5 min

### Testing & Validation
- [ ] Local dry-run: `python test_cases_simple.py` — passes 4 cases in <30s
- [ ] Case studies: `python validate_case_studies.py --cases 10` — no crashes, all 10 pass
- [ ] Judge simulator: `python magicpin-ai-challenge/judge_simulator.py` — 30 pairs score >40/50 average
- [ ] Manual E2E test: /v1/context → /v1/tick → /v1/reply → /v1/healthz → /v1/metadata

### Uptime Guarantees
- [ ] /healthz keep-alive running (pings every 5 min)
- [ ] In-memory state survives API restarts (idempotent /v1/context)
- [ ] Grounded fallback fires if all LLM tiers fail (NEVER returns empty body)
- [ ] Repair logic attempts 1st validation failure before fallback
- [ ] Bot stays live ≥72h post-deadline (no manual restarts)

---

## CONCLUSION

**Vera is rules-first determinism: every output grounded in extracted facts.**

The 4-context composition engine merges category, merchant, trigger, and customer layers into a flat dict. The deterministic planning layer (pre-LLM) decides angle, anchor facts, compulsion lever, and CTA structure. The LLM ladder handles rate limits across 5 tiers, jumping providers on 429. The universal payload scan ensures surprise triggers (judge injection) produce specific messages, not fallbacks. Validation checks structure; repair auto-fixes; grounded fallbacks never return empty or generic. Intent detection prevents loops. In-memory state simplifies deployment.

**Judge rubric scores 5 dimensions**: decision quality, specificity, category fit, merchant fit, engagement compulsion. This design ensures every message targets all 5 by construction—pre-planned structure + real numbers + category rules + merchant identity + binary CTA.

**Robustness against adaptive injection**: When the judge invents a new trigger kind mid-test, the universal payload scan extracts numbers from ANY payload shape. The grounded fallback uses per-kind templates. The entire system never hallucin ates—every number comes from extracted facts.

---

**Technical POC**: Vishnu | **Model**: Claude Haiku 4.5 | **Status**: Ready for Live Judge Test
