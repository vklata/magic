# Vera Bot Case-Study Validation

## Overview

Comprehensive test suite to validate bot outputs against **10 case-study gold standards** from `magicpin-ai-challenge/examples/case-studies.md`.

Each case tests:
- **Specificity** (10/10): Numbers from context, citations
- **Category fit** (10/10): Domain vocabulary, tone, taboos
- **Merchant fit** (10/10): Owner name, locality, real offers
- **Trigger relevance** (10/10): Directly addresses the trigger
- **Engagement compulsion** (9-10/10): CTA clarity, effort externalization, hooks

---

## Scripts Provided

### 1. **`test_cases_simple.py`** — Quick Smoke Test (⭐ START HERE)
**For**: Fast validation of 4 representative cases  
**Endpoint**: Hosted bot (https://kkalra-vera-magicpin.hf.space)  
**Time**: ~30 sec  
**Output**: Signal detection + format checks per case

```bash
python test_cases_simple.py
```

Expected output:
```
✅ Case #1: Dentists / Research Digest
   📡 Status: 200
   ✅ Signal Detection:
      ✅ JIDA
      ✅ meera
      ✅ 2100
      ✅ 38
      ...
   Score: 6/7 signals found
   📊 Dimension Score: 85% signals + 4/4 format checks
```

---

### 2. **`validate_case_studies.py`** — Full Validation (Comprehensive)
**For**: Detailed scoring of all 10 cases  
**Endpoint**: Hosted OR local bot  
**Time**: ~2-3 min  
**Output**: Per-case scores (0-10/dimension) + aggregates + gap analysis

```bash
# Hosted bot
python validate_case_studies.py --bot-url https://kkalra-vera-magicpin.hf.space

# Local bot (requires bot running on port 8080)
python validate_case_studies.py --local

# Test just first 3 cases (faster)
python validate_case_studies.py --cases 3
```

Expected output:
```
================================================================================
🔍 Vera Case Studies Validator
   Bot URL: https://kkalra-vera-magicpin.hf.space
   Case Studies: 10
================================================================================

================================================================================
Case #1
================================================================================

📌 Gold Standard Message:
  Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult...

🤖 Bot Output:
  Dr. Meera, JIDA's recent update shows fluoride recall benefits...

📊 Scores (out of 10):
  ✅ specificity          : bot=9   gold=10  gap=-1
  ✅ category_fit         : bot=10  gold=10  gap=0
  ✅ merchant_fit         : bot=9   gold=10  gap=-1
  ✅ trigger_relevance    : bot=10  gold=10  gap=0
  ⚠️  compulsion          : bot=8   gold=10  gap=-2

✅ Signals Found: merchant_first_name, source_citation, 38pct, reciprocity_offer
❌ Issues:
   - Missing key signals: binary_cta, specific_number_2100

================================================================================
📈 Summary Across 10 Cases
================================================================================

📊 Average Gaps by Dimension (lower is better):
  ✅ specificity          : 0.30 points behind gold
  ✅ category_fit         : 0.50 points behind gold
  ✅ merchant_fit         : 0.80 points behind gold
  ⚠️  trigger_relevance    : 0.20 points behind gold
  ⚠️  compulsion          : 1.20 points behind gold

🏆 Overall: 485/500 (97.0%)
```

---

### 3. **`test_bot_endpoint.py`** — Manual Endpoint Inspection
**For**: Step-by-step debugging of specific cases  
**Endpoint**: Hosted bot only  
**Time**: ~30 sec  
**Output**: Detailed checks for Case #1 & #2

```bash
python test_bot_endpoint.py
```

---

## What Each Dimension Tests

| Dimension | Gold Standard | What to Look For |
|-----------|---------------|------------------|
| **Specificity** (10/10) | Numbers from context; source citations; concrete dates/times | ✅ "2,100-patient trial", "38%", "JIDA Oct 2026 p.14" |
| **Category fit** (10/10) | Domain-specific vocab; correct tone; no taboos | ✅ "fluoride varnish" (not "fluoride paste"), "covers" (not "customers" for restaurants) |
| **Merchant fit** (10/10) | Owner/merchant first name; locality; real offers from catalog | ✅ "Dr. Meera", "Lajpat Nagar", "₹299 cleaning" (real offer) |
| **Trigger relevance** (10/10) | Directly addresses why NOW | ✅ "JIDA's Oct issue landed" (explicitly references the trigger) |
| **Engagement compulsion** (9-10/10) | Effort externalization; curiosity hooks; single binary CTA | ✅ "Want me to draft...? Live in 10 min" (reciprocity + time cap) |

---

## Key Signals Validator Detects

### All Cases:
- ✅ **Merchant first name present** (e.g., "Dr. Meera", "Suresh")
- ✅ **Specific numbers** (not generic: "2,100", "38%", "₹299", not "many", "better", "discount")
- ✅ **Single clear CTA** (binary preferred: "Yes/No", "Reply 1/2", "Want me to...")
- ✅ **Source cited if research claim** (e.g., "JIDA Oct 2026 p.14", batch number)
- ✅ **No URLs** (validated out, -3 penalty if present)
- ✅ **Under 320 chars** (truncated if longer)

### By Case Type:

**Merchant-facing cases** (#1, 4, 5, 6, 7, 9):
- Merchant's first name
- Concrete next step + effort externalization
- Peer benchmark or data point (e.g., "-12% restaurant covers")

**Customer-facing cases** (#2, 3, 8, 10):
- Customer first name (e.g., "Priya", "Kavya", "Rashmi")
- Language preference honored (Hindi-English mix, "Namaste" for seniors)
- Specific dates + times + prices
- No shame/guilt (lapse cases)
- Binary CTA with friction removal ("no commitment, no auto-charge")

---

## Case-Study Gold Standards

All 10 cases extracted from `magicpin-ai-challenge/examples/case-studies.md`:

### Case #1 — Dentists / Research Digest (merchant, 50/50)
**Merchant**: Dr. Meera, Lajpat Nagar Delhi  
**Trigger**: research_digest (JIDA Oct 2026 paper: 3-month fluoride recall vs 6-month, 38% caries reduction)  
**Key signals**: JIDA citation, 2,100 patients, 38%, "high-risk adult patients", reciprocity, binary CTA

---

### Case #2 — Dentists / Recall Reminder (customer, 49/50)
**Customer**: Priya (5mo lapsed, weekday evening pref)  
**Trigger**: recall_due (6-month cleaning recall window)  
**Key signals**: Name, language mix (hi-en), specific slots, ₹299, "complimentary fluoride", multi-choice CTA

---

### Case #3 — Salons / Bridal Followup (customer, 47/50)
**Customer**: Kavya (bride-to-be, wedding Nov 8)  
**Trigger**: bridal_followup  
**Key signals**: 196 days to wedding, skin-prep program, ₹2,499, Saturday 4pm preference, binary commit

---

### Case #4 — Salons / Curious Ask (merchant, 44/50)
**Merchant**: Lakshmi, Studio11 Hyderabad  
**Trigger**: curious_ask_due (weekly "what's in demand?" cadence)  
**Key signals**: Merchant name, low-stakes question, reciprocity (Google post + draft), 5-min effort anchor

---

### Case #5 — Restaurants / IPL Match (merchant, 50/50) ⭐
**Merchant**: Suresh, SK Pizza Junction Delhi  
**Trigger**: ipl_match_today (DC vs MI at 7:30pm)  
**Key signals**: Counter-intuitive data ("-12% restaurant covers on Saturday IPL"), saves merchant from bad decision, existing offer leverage, 10-min cap

---

### Case #6 — Restaurants / Active Planning (merchant, 49/50)
**Merchant**: Suresh, Mylari Bangalore  
**Trigger**: active_planning_intent (corporate thali package)  
**Key signals**: Complete drafted artifact (tiered pricing), concrete radius (Embassy Tech, RMZ Eco, Sigma Soft), follow-on offer

---

### Case #7 — Gyms / Seasonal Dip (merchant, 48/50)
**Merchant**: Karthik, PowerHouse HSR Layout Bangalore  
**Trigger**: seasonal_perf_dip (views -30% in April)  
**Key signals**: Anxiety preemption ("-25 to -35% normal"), reframe as opportunity, member count (245), specific months (Sept-Oct)

---

### Case #8 — Gyms / Lapse Winback (customer, 50/50)
**Customer**: Rashmi (57 days lapsed, weight-loss goal)  
**Trigger**: customer_lapsed_hard  
**Key signals**: Owner name (Karthik), no-shame, addresses past goal (weight loss), specific class (Tue/Thu HIIT 6:30pm), free trial, barrier removal ("no commitment, no auto-charge")

---

### Case #9 — Pharmacies / Supply Alert (merchant, 50/50)
**Merchant**: Ramesh, Apollo Jaipur  
**Trigger**: supply_alert (voluntary recall on atorvastatin batches)  
**Key signals**: Merchant name, batch numbers (AT2024-1102, AT2024-1108), risk bounded ("sub-potency, no safety risk"), derived count (22 of 240 chronic customers), end-to-end workflow

---

### Case #10 — Pharmacies / Chronic Refill (customer, 49/50)
**Customer**: Mr. Sharma (65-75, senior citizen, via son's WhatsApp)  
**Trigger**: chronic_refill_due (metformin/atorvastatin/telmisartan run out 28 Apr)  
**Key signals**: Namaste salutation, molecule names, specific date, total + savings (₹1,420, ₹240 saved), two-channel CTA (reply OR call), senior norms honored

---

## Interpretation Guide

| Signal Pct | Dimension Avg Gap | Status |
|-----------|------------------|--------|
| **90%+** | **<0.5** | 🟢 **Excellent** — Bot matches gold standards closely |
| **75-90%** | **0.5-1.5** | 🟡 **Good** — Minor gaps, likely high judge score |
| **60-75%** | **1.5-3.0** | 🟠 **Fair** — Some missing signals, room to improve |
| **<60%** | **>3.0** | 🔴 **Weak** — Significant gaps, needs investigation |

---

## Debugging Strategy

If bot underperforms:

1. **Check dimension pattern** — which dimension consistently lows? 
   - Low specificity? → Bot not extracting numbers from context
   - Low merchant fit? → Bot not using merchant names from payload
   - Low compulsion? → CTA not binary or effort not externalized

2. **Check trigger handling** — does bot.py dispatch correct kind?
   - `research_digest` → should inject source citation rules
   - `recall_due` → should inject customer language preferences
   - `ipl_match_today` → should add counter-intuitive data rule

3. **Check system prompt** — does it mention:
   - Specificity rules (use context numbers, not fabricate)
   - Category voice (vocab, taboos, tone)
   - Customer fit (language pref, relationship state)
   - Single binary CTA (not multi-ask)

4. **Check LLM model** — temperature=0 required for determinism

---

## Running Locally

### Start the bot:
```bash
# Install
pip install -r requirements.txt

# Set keys
cp .env.example .env
# Edit .env: add OPENROUTER_API_KEY

# Run
uvicorn bot:app --host 0.0.0.0 --port 8080
```

### Then test:
```bash
python validate_case_studies.py --local --cases 3
```

---

## Using Judge Simulator (Authoritative)

The official judge harness in `magicpin-ai-challenge/judge_simulator.py` runs actual LLM-based scoring:

```bash
cd magicpin-ai-challenge
export BOT_URL=https://kkalra-vera-magicpin.hf.space
python judge_simulator.py --scenario full_evaluation
```

This is slower (~10-15 min) but gives true judge scores across all 30 test pairs.

---

## Files

```
vera-magicpin/
├── test_cases_simple.py          ← Quick smoke test (4 cases, ~30s)
├── validate_case_studies.py       ← Full validation (10 cases, ~2min)
├── test_bot_endpoint.py           ← Manual endpoint inspection
├── bot.py                         ← Bot service (contains compose() function)
├── magicpin-ai-challenge/
│   ├── examples/
│   │   └── case-studies.md        ← Gold standards (10 cases with scores)
│   └── judge_simulator.py         ← Authoritative judge harness
└── README.md
```

---

## Quick Start

```bash
# 1. Quick smoke test (30 sec)
python test_cases_simple.py

# 2. Full validation if good (2 min)
python validate_case_studies.py

# 3. Judge simulator if excellent (10-15 min, official)
cd magicpin-ai-challenge && python judge_simulator.py --scenario full_evaluation
```

---

Created: 2026-04-30  
Validator v1.0 — Aligned with case-studies.md patterns
