"""
generate_submission.py
Reads the 30 test pairs from expanded/test_pairs.json,
loads the corresponding dataset JSONs, calls the LLM composer,
and writes submission.jsonl (30 lines, one per test).

Run from repo root:
    python generate_submission.py
"""
import os, json, re, asyncio, time, logging
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gen_submission")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
if not OPENROUTER_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not set")

DATASET_DIR = Path("magicpin-ai-challenge/expanded")
OUT_FILE    = Path("submission.jsonl")

MODEL_LADDER = [
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "meta-llama/llama-3.1-8b-instruct",
    "openrouter/auto",
]

# ─── LLM helpers ──────────────────────────────────────────────────────────────
async def llm_call(model: str, system: str, user: str, timeout: float) -> tuple[str, int]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://magicpin.com",
        "X-Title": "Vera Submission Generator"
    }
    body = {
        "model": model,
        "temperature": 0,          # deterministic as required by the brief
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ],
        "provider": {"order": ["Google", "Groq"], "allow_fallbacks": True},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, json=body
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], 200
            logger.warning(f"[{model}] HTTP {r.status_code}: {r.text[:200]}")
            return "", r.status_code
        except Exception as e:
            logger.error(f"[{model}] error: {e}")
            return "", 0


async def call_llm_ladder(system: str, user: str, budget: float = 20.0) -> str:
    t0 = time.time()
    for model in MODEL_LADDER:
        remaining = budget - (time.time() - t0)
        if remaining < 2:
            break
        text, status = await llm_call(model, system, user, min(remaining - 0.5, 25))
        if status == 200 and text:
            return text
        if status == 429:
            await asyncio.sleep(2)
            text, status = await llm_call(model, system, user, min(budget - (time.time()-t0) - 0.5, 25))
            if status == 200 and text:
                return text
    return '{"body":"Vera here — saw something worth flagging. Want a quick look?","cta":"open_ended","send_as":"vera","suppression_key":"fallback","rationale":"all-tiers-failed fallback"}'


def parse_llm_json(raw: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError(f"No JSON: {raw[:200]}")


# ─── Composer system prompt ────────────────────────────────────────────────────
COMPOSER_SYSTEM = """You are Vera, magicpin's merchant AI assistant. Compose one WhatsApp message.

HARD CONSTRAINTS:
- body ≤ 320 characters (count carefully)
- NO URLs (no http/https)
- NO fabricated data — ONLY facts from the contexts provided
- Single primary CTA: "binary" (YES/STOP), "open_ended", or "none"
- Peer-to-peer tone; NOT promotional hype
- Honor merchant language preference

SCORING DIMENSIONS — maximize ALL 5:
1. SPECIFICITY: ≥2 concrete facts (numbers, dates, named sources)
2. CATEGORY FIT: Match vertical voice + taboos (no "cure"/"guaranteed" for dentists)
3. MERCHANT FIT: Personalized to this specific merchant's data (CTR, offers, signals)
4. TRIGGER RELEVANCE: Clearly explain WHY NOW — reference the trigger kind & payload
5. ENGAGEMENT COMPULSION: One lever (curiosity / loss-aversion / social-proof / effort-externalization / binary-CTA)

TRIGGER-KIND RULES:
- research_digest: cite source, trial N, connect to merchant's patient cohort
- recall_due / customer_lapsed_soft / appointment_tomorrow: patient name, service, specific slots
- perf_dip / perf_spike: exact delta%, metric, vs peer benchmark
- renewal_due: days_remaining, plan, concrete loss if lapsed
- festival_upcoming: festival name, days_until, category-relevant hook
- review_theme_emerged: theme, occurrences_30d, gentle coaching (not blaming)
- competitor_opened: locality, urgency, social-proof angle
- curious_ask_due: open curious question, no data anchor needed
- dormant_with_vera: re-engagement hook based on merchant's best signal
- milestone_reached: celebrate + next goal
- chronic_refill_due: medication name, refill timing, customer name

send_as rules:
- "vera" when scope=merchant (Vera talks TO the merchant)
- "merchant_on_behalf" when scope=customer (Vera drafts a message FROM the merchant to their customer)

ANTI-PATTERNS (lose points):
- "Hi there", "Merchants like you", missing merchant name
- "10% off" without a service name / price
- Long preambles ("I hope you are doing well...")
- Multiple CTAs
- Any URL

Return ONLY valid JSON — no markdown fences:
{"body": "...", "cta": "binary|open_ended|none", "send_as": "vera|merchant_on_behalf", "suppression_key": "...", "rationale": "≤80 chars why"}
"""


def build_user_prompt(category: dict, merchant: dict, trigger: dict, customer: dict | None) -> str:
    lines = [
        "=== CATEGORY CONTEXT ===",
        f"Slug: {category.get('slug','')}",
        f"Voice tone: {category.get('voice',{}).get('tone','')}",
        f"Taboos: {category.get('voice',{}).get('vocab_taboo',[])}",
        f"Peer stats: {json.dumps(category.get('peer_stats',{}))}",
    ]
    digest = category.get("digest", [])
    if digest:
        d = digest[0]
        lines.append(
            f"Top digest item: {d.get('title','')} | Source: {d.get('source','')} "
            f"| N={d.get('trial_n','')} | Segment: {d.get('patient_segment','')}"
        )

    identity = merchant.get("identity", {})
    perf = merchant.get("performance", {})
    lines += [
        "",
        "=== MERCHANT CONTEXT ===",
        f"Name: {identity.get('name','')} | Locality: {identity.get('locality','')} | City: {identity.get('city','')}",
        f"Owner first name: {identity.get('owner_first_name','')}",
        f"Languages: {identity.get('languages',['en'])}",
        f"Subscription: {merchant.get('subscription',{}).get('plan','')} | {merchant.get('subscription',{}).get('days_remaining','')} days left",
        f"Performance 30d: views={perf.get('views','')} calls={perf.get('calls','')} CTR={perf.get('ctr','')} leads={perf.get('leads','')}",
        f"7d delta: {json.dumps(perf.get('delta_7d',{}))}",
        f"Signals: {merchant.get('signals',[])}",
        f"Active offers: {[o['title'] for o in merchant.get('offers',[]) if o.get('status')=='active']}",
        f"Customer aggregate: {json.dumps(merchant.get('customer_aggregate',{}))}",
    ]
    review_themes = merchant.get("review_themes", [])
    if review_themes:
        lines.append(f"Review themes: {review_themes[:2]}")

    lines += [
        "",
        "=== TRIGGER CONTEXT ===",
        f"Kind: {trigger.get('kind','')} | Scope: {trigger.get('scope','')} | Source: {trigger.get('source','')} | Urgency: {trigger.get('urgency','')}",
        f"Payload: {json.dumps(trigger.get('payload',{}))}",
        f"Suppression key: {trigger.get('suppression_key','')}",
        f"Expires at: {trigger.get('expires_at','')}",
    ]

    if customer:
        cid = customer.get("identity", {})
        rel = customer.get("relationship", {})
        lines += [
            "",
            "=== CUSTOMER CONTEXT ===",
            f"Name: {cid.get('name','')} | Language pref: {cid.get('language_pref','')}",
            f"State: {customer.get('state','')} | Visits: {rel.get('visits_total','')}",
            f"Last visit: {rel.get('last_visit','')} | Services received: {rel.get('services_received',[])}",
            f"Preferred slots: {customer.get('preferences',{}).get('preferred_slots','')}",
            f"Consent scope: {customer.get('consent',{}).get('scope',[])}",
        ]

    lines.append("\nCompose the WhatsApp message. Return JSON only.")
    return "\n".join(lines)


# ─── Dataset loaders ───────────────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_file(folder: Path, prefix: str) -> Path | None:
    """Find first file in folder matching prefix."""
    for p in folder.iterdir():
        if p.name.startswith(prefix):
            return p
    return None


def load_ctx(folder: Path, entity_id: str) -> dict | None:
    p = folder / f"{entity_id}.json"
    if p.exists():
        return load_json(p)
    # Try prefix match (filenames may have extra suffixes)
    alt = find_file(folder, entity_id)
    if alt:
        return load_json(alt)
    return None


# ─── Main generator ────────────────────────────────────────────────────────────
async def generate():
    test_pairs_path = DATASET_DIR / "test_pairs.json"
    pairs = load_json(test_pairs_path)["pairs"]

    categories_dir = DATASET_DIR / "categories"
    merchants_dir  = DATASET_DIR / "merchants"
    customers_dir  = DATASET_DIR / "customers"
    triggers_dir   = DATASET_DIR / "triggers"

    results = []

    for i, pair in enumerate(pairs):
        test_id     = pair["test_id"]
        trigger_id  = pair["trigger_id"]
        merchant_id = pair["merchant_id"]
        customer_id = pair.get("customer_id")

        logger.info(f"[{i+1}/30] {test_id}: merchant={merchant_id} trigger={trigger_id} customer={customer_id}")

        # Load contexts
        trigger  = load_ctx(triggers_dir, trigger_id)
        merchant = load_ctx(merchants_dir, merchant_id)
        customer = load_ctx(customers_dir, customer_id) if customer_id else None

        if not trigger:
            logger.error(f"  ✗ trigger not found: {trigger_id}")
            continue
        if not merchant:
            logger.error(f"  ✗ merchant not found: {merchant_id}")
            continue

        category_slug = merchant.get("category_slug", "")
        category = load_ctx(categories_dir, category_slug)
        if not category:
            logger.error(f"  ✗ category not found: {category_slug}")
            continue

        # Compose
        user_prompt = build_user_prompt(category, merchant, trigger, customer)
        raw = await call_llm_ladder(COMPOSER_SYSTEM, user_prompt, budget=25.0)
        try:
            composed = parse_llm_json(raw)
        except Exception as e:
            logger.warning(f"  ✗ JSON parse failed: {e} — using fallback")
            composed = {
                "body": "Quick update worth knowing — reply YES to see details.",
                "cta": "binary",
                "send_as": "vera",
                "suppression_key": trigger.get("suppression_key", f"fallback:{test_id}"),
                "rationale": "parse-failed fallback"
            }

        # Ensure required keys
        scope = trigger.get("scope", "merchant")
        record = {
            "test_id":         test_id,
            "body":            composed.get("body", "")[:320],
            "cta":             composed.get("cta", "open_ended"),
            "send_as":         composed.get("send_as", "vera" if scope == "merchant" else "merchant_on_behalf"),
            "suppression_key": composed.get("suppression_key") or trigger.get("suppression_key", f"gen:{test_id}"),
            "rationale":       composed.get("rationale", "")[:120],
        }
        results.append(record)
        logger.info(f"  ✓ body ({len(record['body'])} chars): {record['body'][:80]}…")

        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)

    # Write JSONL
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info(f"\n✅ Done — {len(results)}/30 pairs written to {OUT_FILE}")

    # Validation summary
    missing = 30 - len(results)
    if missing:
        logger.warning(f"⚠️  {missing} pairs were skipped (context not found). Check logs above.")


if __name__ == "__main__":
    asyncio.run(generate())
