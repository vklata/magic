# Vera Bot: 4-Context Data Access Guide

## Problem: Generic vs Specific

**Generic** (Bad — loses points):
```
Hi Doctor, want to run a discount campaign today to increase sales?
```
- No trigger (why NOW?)
- No merchant fact (which doctor?)
- No category voice (sounds templated)
- High compulsion (generic "increase sales")

**Specific** (Good — case-study gold):
```
190 people in your locality are searching for "Dental Check Up". 
Should I send them a discounted check up at ₹299?
```
- ✅ Trigger: Real demand signal (190 searches)
- ✅ Merchant fact: Locality used ("your locality")
- ✅ Category voice: "Dental Check Up" (actual category language)
- ✅ Real offer: ₹299 (from merchant's offer catalog)
- ✅ Single CTA: "Should I send them..."

---

## Data Sources: 4 Layers

### Layer 1: **CategoryContext**
**File**: `dataset/categories/{slug}.json` (5 files)  
**What bot receives**: Single file per category + trigger kind  
**What bot uses**: Vocab, tone, peer stats, digest items

Example (dentists):
```json
{
  "slug": "dentists",
  "voice": {
    "vocab_allowed": ["fluoride varnish", "caries", "scaling", ...],
    "vocab_taboo": ["guaranteed", "100% safe", "miracle", ...],
    "tone_examples": ["Worth a look — JIDA Oct 2026 p.14", ...]
  },
  "peer_stats": {
    "avg_ctr": 0.030,
    "avg_retention_6mo_pct": 0.42,
    "avg_views_30d": 1820
  },
  "digest": [
    {
      "id": "d_2026W17_jida_fluoride",
      "title": "3-month fluoride varnish recall outperforms 6-month...",
      "source": "JIDA Oct 2026, p.14",
      "trial_n": 2100,
      "summary": "...38% lower caries recurrence..."
    }
  ]
}
```

**Bot uses in compose()**:
- `voice.vocab_allowed` → Don't use taboo words
- `voice.tone_examples` → Match this register
- `peer_stats` → Benchmark comparisons ("you're 12% above peer median CTR")
- `digest` → Source citations ("JIDA p.14 shows...")

---

### Layer 2: **MerchantContext**
**File**: `dataset/merchants/m_{NNN}_{slug}_{city}.json` (50 files)  
**What bot receives**: Triggered merchant's full context  
**What bot uses**: Name, locality, offers, performance, signals

Example (Dr. Meera):
```json
{
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "identity": {
    "name": "Dr. Meera's Dental Clinic",
    "city": "Delhi",
    "locality": "Lajpat Nagar",
    "owner_first_name": "Meera",
    "languages": ["en", "hi"]
  },
  "performance": {
    "views": 2410,
    "ctr": 0.021,
    "calls": 18,
    "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05}
  },
  "offers": [
    {
      "id": "o_meera_001",
      "title": "Dental Cleaning @ ₹299",
      "status": "active"
    },
    {
      "id": "o_meera_002",
      "title": "Deep Cleaning @ ₹499",
      "status": "expired"
    }
  ],
  "customer_aggregate": {
    "total_unique_ytd": 540,
    "lapsed_180d_plus": 78,
    "high_risk_adult_count": 124
  },
  "signals": ["stale_posts:22d", "ctr_below_peer_median", "high_risk_adult_cohort"],
  "conversation_history": [
    {
      "ts": "2026-04-24T10:12:00Z",
      "from": "vera",
      "body": "Profile audit done...",
      "engagement": "merchant_replied"
    }
  ]
}
```

**Bot uses in compose()**:
- `identity.owner_first_name` → "Dr. Meera" (not "the clinic")
- `identity.locality` → "Lajpat Nagar" (hyperlocal specificity)
- `performance.ctr` + `peer_stats.avg_ctr` → "You're 30% below peer median"
- `offers[active]` → "Your ₹299 cleaning" (real offer, not imagined)
- `customer_aggregate` → "124 high-risk adult patients in your roster"
- `signals` → "Your posts are stale — 22 days since last"
- `conversation_history` → "You just replied to the profile audit..."

---

### Layer 3: **TriggerContext**
**File**: `dataset/triggers/trg_{NNN}_{kind}.json` (100 files)  
**What bot receives**: Triggered event's full context  
**What bot uses**: Kind-specific payload, urgency, expiry

Example (research_digest for Dr. Meera):
```json
{
  "id": "trg_001_research_digest_dentists",
  "scope": "merchant",
  "kind": "research_digest",
  "source": "external",
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "customer_id": null,
  "payload": {
    "category": "dentists",
    "top_item_id": "d_2026W17_jida_fluoride"
  },
  "urgency": 2,
  "suppression_key": "research:dentists:2026-W17",
  "expires_at": "2026-05-03T00:00:00Z"
}
```

Example (recall_due for Priya):
```json
{
  "id": "trg_003_recall_due_priya",
  "scope": "customer",
  "kind": "recall_due",
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "customer_id": "c_001_priya_for_m001",
  "payload": {
    "service_due": "6_month_cleaning",
    "last_service_date": "2026-05-12",
    "due_date": "2026-11-12",
    "available_slots": [
      {"iso": "2026-11-05T18:00:00+05:30", "label": "Wed 5 Nov, 6pm"},
      {"iso": "2026-11-06T17:00:00+05:30", "label": "Thu 6 Nov, 5pm"}
    ]
  },
  "urgency": 3,
  "suppression_key": "recall:c_001_priya_for_m001:6mo",
  "expires_at": "2026-11-30T00:00:00Z"
}
```

**Bot uses in compose()**:
- `kind` → Dispatch to kind-specific system prompt rules
- `payload.top_item_id` → Look up the digest item in CategoryContext
- `payload.available_slots` → "Wed 5 Nov, 6pm ya Thu 6 Nov, 5pm" (exact dates from payload)
- `urgency` → High urgency = shorter message, crisper CTA
- `suppression_key` → Track if already sent (global dedup)

---

### Layer 4: **CustomerContext** (Optional)
**File**: `dataset/customers/c_{NNN}_{name}_for_m_{MMM}.json` (200 files)  
**What bot receives**: If customer_id present in trigger  
**What bot uses**: Name, preferences, relationship state, consent

Example (Priya):
```json
{
  "customer_id": "c_001_priya_for_m001",
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "identity": {
    "name": "Priya",
    "language_pref": "hi-en mix",
    "age_band": "25-35"
  },
  "relationship": {
    "first_visit": "2025-11-04",
    "last_visit": "2026-05-12",
    "visits_total": 4,
    "services_received": ["cleaning", "cleaning", "whitening", "cleaning"],
    "lifetime_value": 1696
  },
  "state": "lapsed_soft",
  "preferences": {
    "preferred_slots": "weekday_evening",
    "channel": "whatsapp",
    "reminder_opt_in": true
  },
  "consent": {
    "opted_in_at": "2025-11-04",
    "scope": ["recall_reminders", "appointment_reminders"]
  }
}
```

Example (Mr. Sharma, senior):
```json
{
  "customer_id": "c_010_sharma_for_m009",
  "identity": {
    "name": "Mr. Sharma",
    "language_pref": "hindi_hinglish",
    "age_band": "65-75"
  },
  "state": "active_chronic",
  "preferences": {
    "channel": "whatsapp",
    "reminder_opt_in": true,
    "contact_via_son": true
  }
}
```

**Bot uses in compose()**:
- `identity.name` → "Hi Priya" (not "Hi customer")
- `identity.language_pref` → "hi-en mix" → Use "Apke liye 2 slots ready hain: ... ya ..."
- `state` → "lapsed_soft" → No shame, emphasize how easy to return
- `preferences.preferred_slots` → "Weekday evening" → Offer only evening slots
- `preferences.contact_via_son` → "Namaste" salutation, formal tone for respect

---

## Composition Flow

```
Bot receives:
  + category_slug
  + merchant_id
  + trigger_id
  + customer_id (optional)

Bot fetches:
  1. CategoryContext (from categories/{slug}.json)
  2. MerchantContext (from merchants/m_NNN.json)
  3. TriggerContext (from triggers/trg_NNN.json)
  4. CustomerContext (from customers/c_NNN.json, if customer_id present)

Bot dispatches by trigger.kind:
  "research_digest"           → Inject source citation rules
  "recall_due"               → Inject slot formatting + language pref
  "ipl_match_today"          → Inject counter-intuitive data rules
  "seasonal_dip"             → Inject reframe + peer benchmark
  "customer_lapsed_hard"     → Inject no-shame voice
  "bridal_followup"          → Inject wedding countdown + urgency
  "supply_alert"             → Inject compliance + batch numbers
  etc.

Bot composes using:
  - Category voice (vocab, tone, taboos)
  - Merchant fact (owner name, locality, active offer, performance delta)
  - Trigger payload (specific numbers, dates, items)
  - Customer pref (language, slots, state)

Result: Specific message like:
  "Hi Priya, Dr. Meera's clinic here 🦷 It's been 5 months since your 
   last visit — your 6-month cleaning recall is due. Apke liye 2 slots 
   ready hain: Wed 5 Nov, 6pm ya Thu 6 Nov, 5pm. ₹299 cleaning + 
   complimentary fluoride. Reply 1 for Wed, 2 for Thu, or tell us a 
   time that works."
```

---

## Key Numbers to Inject (Specificity)

| Dimension | Where to Get | Example |
|-----------|-------------|---------|
| **Merchant numbers** | `MerchantContext.performance` | "Your CTR is 2.1% vs peer avg 3.0%" |
| **Customer numbers** | `MerchantContext.customer_aggregate` | "124 high-risk adults in your roster" |
| **Trigger numbers** | `TriggerContext.payload` | "190 people searching for Dental Check Up" |
| **Research numbers** | `CategoryContext.digest[item]` | "2,100-patient trial showed 38% better" |
| **Offer numbers** | `MerchantContext.offers[active]` | "₹299 cleaning" |
| **Peer benchmarks** | `CategoryContext.peer_stats` | "-25 to -35% normal April-June dip" |
| **Time numbers** | `TriggerContext.payload` | "Wed 5 Nov 6pm, Thu 6 Nov 5pm" |
| **Cohort numbers** | `MerchantContext.customer_aggregate` or trigger payload | "22 of your 240 chronic-Rx customers" |

---

## What Each Layer Does

| Layer | File Type | Count | Per-Category | Role |
|-------|-----------|-------|--------------|------|
| **Category** | categories/{slug}.json | 5 | 1 | Vocab, voice, peer stats, digest items |
| **Merchant** | merchants/m_NNN.json | 50 | 10 | Name, offers, performance, signals |
| **Trigger** | triggers/trg_NNN.json | 100 | 20 | Event payload, kind, urgency, slots |
| **Customer** | customers/c_NNN.json | 200 | 40 | Name, prefs, language, state, consent |

---

## 30 Test Pairs: What Bot Gets

The challenge defines **30 canonical test pairs** in `expanded/test_pairs.json`:

Each pair is:
```json
{
  "case_id": 1,
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "trigger_id": "trg_001_research_digest_dentists",
  "customer_id": null,
  "expected_scope": "merchant"
}
```

For each pair, bot receives:
1. `CategoryContext` from categories/dentists.json
2. `MerchantContext` from merchants/m_001_drmeera_dentist_delhi.json
3. `TriggerContext` from triggers/trg_001_research_digest_dentists.json
4. `CustomerContext` from customers/... (if customer_id != null)

Then composes a message.

Judge scores on 5 dimensions (50 total points):
- **Specificity** (10): Numbers, citations, concrete details
- **Category fit** (10): Vocab, tone, no taboos
- **Merchant fit** (10): Owner name, locality, real offer
- **Trigger relevance** (10): Addresses why NOW
- **Engagement compulsion** (10): Clear CTA, effort externalization

---

## How to Access Data in bot.py

```python
# Load category context
def load_category(slug: str) -> dict:
    with open(f"magicpin-ai-challenge/dataset/categories/{slug}.json") as f:
        return json.load(f)

# Load merchant context
def load_merchant(merchant_id: str) -> dict:
    with open(f"magicpin-ai-challenge/dataset/merchants/{merchant_id}.json") as f:
        return json.load(f)

# Load trigger context
def load_trigger(trigger_id: str) -> dict:
    with open(f"magicpin-ai-challenge/dataset/triggers/{trigger_id}.json") as f:
        return json.load(f)

# Load customer context (if customer_id present)
def load_customer(customer_id: str) -> dict:
    with open(f"magicpin-ai-challenge/dataset/customers/{customer_id}.json") as f:
        return json.load(f)

# Compose message using all 4 contexts
def compose(
    category_slug: str,
    merchant_id: str,
    trigger_id: str,
    customer_id: Optional[str] = None
) -> dict:
    category = load_category(category_slug)
    merchant = load_merchant(merchant_id)
    trigger = load_trigger(trigger_id)
    customer = load_customer(customer_id) if customer_id else None
    
    # Build system prompt with category voice + trigger rules
    system = build_system_prompt(category, trigger)
    
    # Build user prompt with merchant + trigger + customer facts
    user = build_user_prompt(merchant, trigger, customer, category)
    
    # Call LLM
    response = llm_call(system, user)
    
    # Extract message
    return {
        "message": response,
        "merchant_id": merchant_id,
        "trigger_id": trigger_id,
        "customer_id": customer_id or None,
        "category": category_slug
    }
```

---

## Validation: What Judges Check

1. **Specificity** — Numbers come from actual context data?
   - ❌ "Lots of people in your area" → Generic
   - ✅ "190 people in your locality searching for Dental Check Up" → Specific (from trigger payload)

2. **Category fit** — Vocabulary correct?
   - ❌ "Your dental patients" (generic)
   - ✅ "high-risk adult cohort", "fluoride varnish", "OPG" (from category vocab_allowed)

3. **Merchant fit** — Uses actual merchant data?
   - ❌ "Hi there" (no name)
   - ✅ "Dr. Meera" (from merchant.identity.owner_first_name)
   - ✅ "Lajpat Nagar" (from merchant.identity.locality)
   - ✅ "₹299 cleaning" (from merchant.offers[active])

4. **Trigger relevance** — Why NOW?
   - ❌ "Want to increase sales?" (no trigger)
   - ✅ "JIDA's Oct issue landed" (explicit trigger.kind + payload)

5. **Engagement compulsion** — Single clear CTA?
   - ❌ "Should I do X, Y, or Z?" (too many asks)
   - ✅ "Want me to draft...? Live in 10 min" (binary, effort externalized)

---

## Files to Load

All data files are in: `magicpin-ai-challenge/dataset/`

```
dataset/
├── categories/
│   ├── dentists.json        → 5-cat contexts (voice, offers, digest, peers)
│   ├── salons.json
│   ├── restaurants.json
│   ├── gyms.json
│   └── pharmacies.json
├── merchants_seed.json      → 10 seed merchants (for reference)
├── customers_seed.json      → 15 seed customers (for reference)
├── triggers_seed.json       → 25 seed triggers (for reference)
└── generate_dataset.py      → Expands seeds to 50/200/100/30

expanded/ (generated by generate_dataset.py):
├── categories/              → Same 5 copied
├── merchants/               → 50 merchant JSON files
├── customers/               → 200 customer JSON files
├── triggers/                → 100 trigger JSON files
└── test_pairs.json          → 30 (merchant, trigger, customer) pairs
```

---

## Summary

**Bad bot** (Generic):
- Ignores merchant name, offer details, customer prefs
- Uses broad statements ("increase sales", "run campaign")
- No numbers, no specificity

**Good bot** (Specific):
- Injects `merchant.identity.owner_first_name`
- Uses `merchant.offers[active].title` + `merchant.offers[active].value`
- Pulls numbers from trigger.payload, merchant.customer_aggregate, category.digest
- Respects `customer.preferences.language_pref` (hi-en mix, not just English)
- Derives numbers (`customer_aggregate.high_risk_adult_count` vs peer_stats.avg)
- Has single, clear CTA with effort externalization

**Example**: Instead of *"Hi Doctor, want to run a discount campaign?"*  
Say: *"Hi Dr. Meera, 190 people in Lajpat Nagar searching for 'Dental Check Up' this week. Should I send them your ₹299 cleaning offer (usually ₹400)? I can draft the WhatsApp + Google post by 10am."*

---

Created: 2026-04-30
