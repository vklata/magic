#!/usr/bin/env python3
"""
Vera Adversarial Judge — Real-Judge Stress Test
================================================

Tests every edge case the real judge could throw:
- Novel/unseen trigger kinds with sparse payloads
- Thin payloads with no numeric data
- Category voice violations
- Boilerplate detection
- Hostile & off-topic merchant replies
- Auto-reply loops
- Intent transitions
- Adaptive injection of new payload fields
- Multi-category cross-contamination
- Replay scenarios

Structure mirrors judge_simulator.py exactly.
Run: TEST_SCENARIO=adversarial python vera_adversarial_judge.py
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

# =============================================================================
# ██████ CONFIGURATION - EDIT THIS SECTION ██████
# =============================================================================

# BOT_URL = os.getenv("BOT_URL", "http://localhost:8080")
BOT_URL = os.getenv("BOT_URL", "https://kkalra-vera-magicpin.hf.space")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
LLM_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "openrouter/auto")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
TEST_SCENARIO = os.getenv("TEST_SCENARIO", "adversarial")

TIMEOUT_LLM = int(os.getenv("TIMEOUT_LLM", "45"))
DATASET_DIR = Path(os.getenv("DATASET_DIR", Path(__file__).parent / "expanded"))

# =============================================================================
# ██████ END CONFIGURATION ██████
# =============================================================================

import sys
import json
import time
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from urllib import request as urlrequest, error as urlerror
from abc import ABC, abstractmethod



# =============================================================================
# TERMINAL OUTPUT  (identical helpers to judge_simulator.py)
# =============================================================================

class Colors:
    HEADER  = '\033[95m'; BLUE   = '\033[94m'; CYAN   = '\033[96m'
    GREEN   = '\033[92m'; YELLOW = '\033[93m'; RED    = '\033[91m'
    MAGENTA = '\033[35m'; BOLD   = '\033[1m';  DIM    = '\033[2m'
    RESET   = '\033[0m'

def print_header(t):  print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}\n{t.center(70)}\n{'='*70}{Colors.RESET}\n")
def print_section(t): print(f"\n{Colors.CYAN}{Colors.BOLD}--- {t} ---{Colors.RESET}\n")
def print_success(t): print(f"{Colors.GREEN}[PASS]{Colors.RESET} {t}")
def print_fail(t):    print(f"{Colors.RED}[FAIL]{Colors.RESET} {t}")
def print_warn(t):    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {t}")
def print_info(t):    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {t}")
def print_llm(t):     print(f"{Colors.MAGENTA}[LLM]{Colors.RESET} {t}")
def print_reason(t):  print(f"  {Colors.DIM}{t[:200]}{'...' if len(t)>200 else ''}{Colors.RESET}")
def print_hint(t):    print(f"\n  {Colors.YELLOW}Hint:{Colors.RESET} {t}")

def print_score_bar(dim, score, max_score=10):
    filled = int((score / max_score) * 20)
    color  = Colors.GREEN if score >= 7 else Colors.YELLOW if score >= 4 else Colors.RED
    print(f"  {dim:24} [{color}{'█'*filled}{Colors.DIM}{'░'*(20-filled)}{Colors.RESET}] {color}{score:2}/{max_score}{Colors.RESET}")

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ScoreResult:
    specificity: int = 0;           specificity_reason: str = ""
    category_fit: int = 0;          category_fit_reason: str = ""
    merchant_fit: int = 0;          merchant_fit_reason: str = ""
    decision_quality: int = 0;      decision_quality_reason: str = ""
    engagement_compulsion: int = 0; engagement_reason: str = ""
    penalties: int = 0;             penalty_reasons: List[str] = field(default_factory=list)
    hint: str = "";                 case_label: str = ""

    @property
    def total(self): return max(0, self.specificity + self.category_fit +
                                   self.merchant_fit + self.decision_quality +
                                   self.engagement_compulsion - self.penalties)

# =============================================================================
# LLM PROVIDERS  (same as judge_simulator.py)
# =============================================================================

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, system: str = None) -> str: pass
    @abstractmethod
    def name(self) -> str: pass

class OpenAIProvider(LLMProvider):
    def __init__(self, k, m=""): self.api_key=k; self.model=m or "gpt-4o-mini"
    def name(self): return f"OpenAI ({self.model})"
    def complete(self, prompt, system=None):
        msgs = ([{"role":"system","content":system}] if system else []) + [{"role":"user","content":prompt}]
        req = urlrequest.Request("https://api.openai.com/v1/chat/completions",
            data=json.dumps({"model":self.model,"messages":msgs,"temperature":0.2,"max_tokens":1500}).encode(),
            headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"})
        return json.loads(urlrequest.urlopen(req,timeout=TIMEOUT_LLM).read())["choices"][0]["message"]["content"]

class OpenRouterProvider(LLMProvider):
    def __init__(self, k, m=""): self.api_key=k; self.model=m or "anthropic/claude-3-haiku"
    def name(self): return f"OpenRouter ({self.model})"
    def complete(self, prompt, system=None):
        msgs = ([{"role":"system","content":system}] if system else []) + [{"role":"user","content":prompt}]
        req = urlrequest.Request("https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({"model":self.model,"messages":msgs,"temperature":0.2,"max_tokens":1500}).encode(),
            headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json","HTTP-Referer":"https://magicpin.com"})
        return json.loads(urlrequest.urlopen(req,timeout=TIMEOUT_LLM).read())["choices"][0]["message"]["content"]

class GroqProvider(LLMProvider):
    def __init__(self, k, m=""): self.api_key=k; self.model=m or "llama-3.3-70b-versatile"
    def name(self): return f"Groq ({self.model})"
    def complete(self, prompt, system=None):
        msgs = ([{"role":"system","content":system}] if system else []) + [{"role":"user","content":prompt}]
        req = urlrequest.Request("https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps({"model":self.model,"messages":msgs,"temperature":0.2,"max_tokens":1500}).encode(),
            headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"})
        return json.loads(urlrequest.urlopen(req,timeout=TIMEOUT_LLM).read())["choices"][0]["message"]["content"]

class GeminiProvider(LLMProvider):
    def __init__(self, k, m=""): self.api_key=k; self.model=m or "gemini-1.5-flash"
    def name(self): return f"Gemini ({self.model})"
    def complete(self, prompt, system=None):
        full = f"{system}\n\n{prompt}" if system else prompt
        req = urlrequest.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
            data=json.dumps({"contents":[{"parts":[{"text":full}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":1500}}).encode(),
            headers={"Content-Type":"application/json"})
        return json.loads(urlrequest.urlopen(req,timeout=TIMEOUT_LLM).read())["candidates"][0]["content"]["parts"][0]["text"]

class OllamaProvider(LLMProvider):
    def __init__(self, m="", url=""): self.model=m or "llama3"; self.api_url=url or "http://localhost:11434"
    def name(self): return f"Ollama ({self.model})"
    def complete(self, prompt, system=None):
        full = f"{system}\n\n{prompt}" if system else prompt
        req = urlrequest.Request(f"{self.api_url}/api/generate",
            data=json.dumps({"model":self.model,"prompt":full,"stream":False,"options":{"temperature":0.2}}).encode(),
            headers={"Content-Type":"application/json"})
        return json.loads(urlrequest.urlopen(req,timeout=90).read())["response"]

def create_provider():
    p = {"openai": lambda: OpenAIProvider(LLM_API_KEY, LLM_MODEL),
         "openrouter": lambda: OpenRouterProvider(LLM_API_KEY, LLM_MODEL),
         "groq": lambda: GroqProvider(LLM_API_KEY, LLM_MODEL),
         "gemini": lambda: GeminiProvider(LLM_API_KEY, LLM_MODEL),
         "ollama": lambda: OllamaProvider(LLM_MODEL, OLLAMA_URL)}
    if LLM_PROVIDER not in p: print_fail(f"Unknown: {LLM_PROVIDER}"); sys.exit(1)
    return p[LLM_PROVIDER]()

# =============================================================================
# DATASET LOADER
# =============================================================================

class DatasetLoader:
    def __init__(self, dataset_dir: Path):
        self.dataset_dir = dataset_dir
        self.categories: Dict[str, dict] = {}
        self.merchants:  Dict[str, dict] = {}
        self.customers:  Dict[str, dict] = {}
        self.triggers:   Dict[str, dict] = {}

    def load(self) -> bool:
        try:
            # New format (subdirectories)
            for sub, store, key in [
                ("categories", self.categories, "slug"),
                ("merchants",  self.merchants,  "merchant_id"),
                ("customers",  self.customers,  "customer_id"),
                ("triggers",   self.triggers,   "id"),
            ]:
                d = self.dataset_dir / sub
                if d.exists() and d.is_dir():
                    for f in d.glob("*.json"):
                        try:
                            data = json.load(open(f, encoding="utf-8"))
                            item_id = data.get(key, f.stem)
                            store[item_id] = data
                        except Exception: pass

            # Legacy format (seed files in root)
            for fname, store, key in [
                ("merchants_seed.json", self.merchants, "merchant_id"),
                ("customers_seed.json", self.customers, "customer_id"),
                ("triggers_seed.json",  self.triggers,  "id"),
            ]:
                p = self.dataset_dir / fname
                if p.exists():
                    try:
                        raw = json.load(open(p, encoding="utf-8"))
                        container = next((k for k, v in raw.items() if isinstance(v, list)), None)
                        if container:
                            for item in raw[container]:
                                if key in item:
                                    store[item[key]] = item
                    except Exception: pass
            
            print_info(f"Loaded dataset: {len(self.categories)} cats, {len(self.merchants)} merchants, {len(self.triggers)} triggers")
            return True
        except Exception as e:
            print_fail(f"Dataset load error: {e}")
            return False

# =============================================================================
# BOT CLIENT  (identical to judge_simulator.py)
# =============================================================================

class BotClient:
    def __init__(self, base_url): self.base_url = base_url.rstrip("/")

    def _request(self, method, path, timeout=30, body_dict=None):
        url   = f"{self.base_url}{path}"
        start = time.time()
        body  = json.dumps(body_dict).encode() if body_dict else None
        req   = urlrequest.Request(url, data=body, method=method,
                                   headers={"Content-Type":"application/json"})
        try:
            resp = urlrequest.urlopen(req, timeout=timeout)
            return json.loads(resp.read()), None, (time.time()-start)*1000
        except urlerror.HTTPError as e:
            lat = (time.time()-start)*1000
            try:    return json.loads(e.read()), None, lat
            except: return None, f"HTTP {e.code}", lat
        except Exception as e:
            return None, str(e), (time.time()-start)*1000

    def healthz(self):            return self._request("GET",  "/v1/healthz", 5)
    def metadata(self):           return self._request("GET",  "/v1/metadata", 5)
    def push_context(self,s,c,v,p):
        return self._request("POST","/v1/context",10,
            {"scope":s,"context_id":c,"version":v,"payload":p,
             "delivered_at":datetime.utcnow().isoformat()+"Z"})
    def tick(self, triggers):
        return self._request("POST","/v1/tick",30,
            {"now":datetime.utcnow().isoformat()+"Z","available_triggers":triggers})
    def reply(self, conv_id, mid, message, turn):
        return self._request("POST","/v1/reply",15,
            {"conversation_id":conv_id,"merchant_id":mid,"customer_id":None,
             "from_role":"merchant","message":message,
             "received_at":datetime.utcnow().isoformat()+"Z","turn_number":turn})

# =============================================================================
# LLM SCORING ENGINE  (same system prompt as judge_simulator.py)
# =============================================================================

JUDGE_SYSTEM = """You are a STRICT judge for the magicpin AI Challenge. You score merchant engagement messages.

SCORING DIMENSIONS (0-10 each, be strict — 5 is average, 7+ is good, 9+ is excellent):

1. SPECIFICITY: Does the message have VERIFIABLE facts?
   - Numbers (percentages, counts, prices, dates)
   - Source citations, data references
   - Concrete claims vs vague statements
   - HARD FAIL (<4): "many customers", "great results", invented numbers

2. CATEGORY FIT: Does the voice match the business type?
   - Dentists: clinical, peer-to-peer, Dr. prefix always
   - Salons: warm, friendly, aspirational
   - Restaurants: operator-to-operator, footfall/covers focus
   - Gyms: coaching, motivational, member-focused
   - Pharmacies: trustworthy, precise, compliance-aware
   - HARD FAIL (<4): promotional tone to a dentist, clinical to a restaurant

3. MERCHANT FIT: Personalized to THIS merchant?
   - Uses owner first name (not "Hi Doctor", "Dear Merchant")
   - References their actual locality and real data
   - HARD FAIL (<4): fabricated data, generic "your store"

4. DECISION QUALITY: Clear WHY NOW + ONE decision?
   - What the merchant must decide TODAY
   - Why acting today matters vs tomorrow
   - HARD FAIL (<4): vague nudge, no decision stated

5. ENGAGEMENT COMPULSION: Would they reply?
   - Loss aversion, curiosity, social proof
   - Single binary CTA or specific open CTA
   - HARD FAIL (<4): "let me know", multi-ask, no CTA

PENALTIES:
- Fabricated data not in context: -2
- URL in body: -3
- Boilerplate opener (Hi, Hello, I hope, Vera here): -2
- Body >320 chars: -2
- Multiple CTAs: -1

RESPOND ONLY WITH THIS EXACT JSON FORMAT:
{
  "specificity": <0-10>,
  "specificity_reason": "",
  "category_fit": <0-10>,
  "category_fit_reason": "",
  "merchant_fit": <0-10>,
  "merchant_fit_reason": "",
  "decision_quality": <0-10>,
  "decision_quality_reason": "",
  "engagement_compulsion": <0-10>,
  "engagement_reason": "",
  "penalties": <0-10>,
  "penalty_reasons": [],
  "hint": ""
}"""

class LLMScorer:
    def __init__(self, llm): self.llm = llm

    def score(self, action, category, merchant, trigger, customer=None, label="") -> ScoreResult:
        body = action.get("body","")
        prompt = f"""ADVERSARIAL TEST CASE: {label}

=== CONTEXT SENT TO BOT ===
Category: {category.get('slug','unknown')}
Voice tone: {category.get('voice',{}).get('tone','unknown')}
Taboo words: {category.get('voice',{}).get('vocab_taboo',[])[:5]}

Merchant name: {merchant.get('identity',{}).get('name','unknown')}
Owner first name: {merchant.get('identity',{}).get('owner_first_name','unknown')}
Locality: {merchant.get('identity',{}).get('locality','unknown')}
Language: {merchant.get('identity',{}).get('languages',[])}
Performance: views={merchant.get('performance',{}).get('views','?')}, calls={merchant.get('performance',{}).get('calls','?')}, ctr={merchant.get('performance',{}).get('ctr','?')}
Signals: {merchant.get('signals',[])}
Active Offers: {[o.get('title') for o in merchant.get('offers',[]) if o.get('status')=='active']}

Trigger Kind: {trigger.get('kind','unknown')} ← may be novel/unseen
Trigger Payload (FULL): {json.dumps(trigger.get('payload',{}))}
Trigger Urgency: {trigger.get('urgency','?')}

Customer: {json.dumps(customer.get('identity',{})) if customer else 'None (merchant-facing)'}

=== BOT RESPONSE ===
Body ({len(body)} chars): "{body}"
CTA: {action.get('cta','none')}
Send As: {action.get('send_as','vera')}

THIS IS AN ADVERSARIAL TEST. Score strictly. If the bot produced generic text despite
having payload data available, penalize specificity and decision_quality hard."""

        try:
            print_llm(f"Scoring: {label}")
            resp = self.llm.complete(prompt, JUDGE_SYSTEM)
            return self._parse(resp, label)
        except Exception as e:
            print_warn(f"LLM error: {e}")
            return self._fallback(action, label)

    def _parse(self, resp, label) -> ScoreResult:
        m = re.search(r'\{[\s\S]*\}', resp)
        if not m: return self._fallback({}, label)
        try:
            d = json.loads(m.group())
            pens = int(d.get("penalties",0))
            pens += 3 if re.search(r'https?://', d.get("body","")) else 0
            return ScoreResult(
                specificity=min(10,max(0,int(d.get("specificity",5)))),
                specificity_reason=d.get("specificity_reason",""),
                category_fit=min(10,max(0,int(d.get("category_fit",5)))),
                category_fit_reason=d.get("category_fit_reason",""),
                merchant_fit=min(10,max(0,int(d.get("merchant_fit",5)))),
                merchant_fit_reason=d.get("merchant_fit_reason",""),
                decision_quality=min(10,max(0,int(d.get("decision_quality",5)))),
                decision_quality_reason=d.get("decision_quality_reason",""),
                engagement_compulsion=min(10,max(0,int(d.get("engagement_compulsion",5)))),
                engagement_reason=d.get("engagement_reason",""),
                penalties=min(10,max(0,pens)),
                penalty_reasons=d.get("penalty_reasons",[]),
                hint=d.get("hint",""),
                case_label=label
            )
        except Exception as e:
            print_warn(f"Parse error: {e}")
            return self._fallback({}, label)

    def _fallback(self, action, label) -> ScoreResult:
        body = action.get("body","").lower()
        nums = len(re.findall(r'\d+', body))
        return ScoreResult(specificity=min(10,3+nums*2), specificity_reason="Fallback: counted numbers",
                           category_fit=5, merchant_fit=5, decision_quality=5, engagement_compulsion=5,
                           hint="LLM failed — heuristic only", case_label=label)

# =============================================================================
# ADVERSARIAL TEST CASES
# =============================================================================
# Each case has: label, category_override, merchant_override, trigger_override,
#                customer_override (optional), expected_min_score (soft target)
# =============================================================================

ADVERSARIAL_CASES = [

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP A: NOVEL / UNSEEN TRIGGER KINDS  (adaptive injection simulation)
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "A1 — Novel kind: marketplace_fraud_alert (rich payload)",
        "category": {"slug":"pharmacies","voice":{"tone":"trustworthy, utility-focused","vocab_taboo":["miracle","cure all"]}},
        "merchant": {"identity":{"name":"MedPlus Pharmacy","owner_first_name":"Rajesh","locality":"Sector 18 Noida","languages":["Hindi","English"]},
                     "performance":{"views":1420,"calls":38,"ctr":2.7},"signals":[],"offers":[{"title":"10% off on generics","status":"active"}]},
        "trigger": {"kind":"marketplace_fraud_alert","urgency":"critical",
                    "payload":{"alert_type":"counterfeit_batch","affected_skus":3,"batch_code":"BT-2024-1187",
                               "flagged_by":"CDSCO","action_deadline_hours":24,"risk_level":0.91}},
        "expected_min": 32
    },
    {
        "label": "A2 — Novel kind: ai_upsell_window (thin payload, only 1 number)",
        "category": {"slug":"restaurants","voice":{"tone":"operator-to-operator","vocab_taboo":["best ever","amazing food"]}},
        "merchant": {"identity":{"name":"Biryani Bros","owner_first_name":"Sameer","locality":"Koramangala","languages":["English"]},
                     "performance":{"views":3200,"calls":91,"ctr":2.8},"signals":[],"offers":[]},
        "trigger": {"kind":"ai_upsell_window","urgency":"medium",
                    "payload":{"window_score":0.83}},  # sparse — only 1 useful field
        "expected_min": 20
    },
    {
        "label": "A3 — Novel kind: carbon_credit_opportunity (completely empty payload)",
        "category": {"slug":"restaurants","voice":{"tone":"operator-to-operator","vocab_taboo":["best ever"]}},
        "merchant": {"identity":{"name":"Cafe Zest","owner_first_name":"Priya","locality":"HSR Layout","languages":["English"]},
                     "performance":{"views":890,"calls":22,"ctr":2.5},"signals":[],"offers":[]},
        "trigger": {"kind":"carbon_credit_opportunity","urgency":"low","payload":{}},
        "expected_min": 15  # bare minimum — payload is empty
    },
    {
        "label": "A4 — Novel kind: competitive_pricing_alert (multiple numbers in payload)",
        "category": {"slug":"salons","voice":{"tone":"warm, aspirational","vocab_taboo":["cheap","discount salon"]}},
        "merchant": {"identity":{"name":"Glam Studio","owner_first_name":"Neha","locality":"Indiranagar","languages":["English"]},
                     "performance":{"views":2100,"calls":67,"ctr":3.2},"signals":[],"offers":[{"title":"Bridal Package ₹4999","status":"active"}]},
        "trigger": {"kind":"competitive_pricing_alert","urgency":"high",
                    "payload":{"competitor_name":"Looks Salon","competitor_price":3499,
                               "your_price":4999,"category_median":4200,"gap_pct":43}},
        "expected_min": 30
    },
    {
        "label": "A5 — Novel kind: health_inspection_due (deadline + numeric risk)",
        "category": {"slug":"pharmacies","voice":{"tone":"trustworthy, compliance-aware","vocab_taboo":["miracle"]}},
        "merchant": {"identity":{"name":"Apollo Pharmacy Lajpat","owner_first_name":"Vivek","locality":"Lajpat Nagar","languages":["Hindi"]},
                     "performance":{"views":980,"calls":29,"ctr":3.0},"signals":[],"offers":[]},
        "trigger": {"kind":"health_inspection_due","urgency":"critical",
                    "payload":{"inspection_date":"2026-05-08","days_remaining":6,"last_score":74,
                               "min_passing_score":80,"checklist_items_pending":4}},
        "expected_min": 35
    },
    {
        "label": "A6 — Novel kind: weather_demand_surge (geo + numeric surge data)",
        "category": {"slug":"restaurants","voice":{"tone":"operator-to-operator","vocab_taboo":["best ever"]}},
        "merchant": {"identity":{"name":"Garam Chai House","owner_first_name":"Arun","locality":"MG Road Pune","languages":["Marathi","English"]},
                     "performance":{"views":4100,"calls":210,"ctr":5.1},"signals":[],"offers":[{"title":"Masala Chai ₹49","status":"active"}]},
        "trigger": {"kind":"weather_demand_surge","urgency":"high",
                    "payload":{"rain_probability_pct":88,"demand_uplift_pct":34,
                               "peak_window_start":"17:00","peak_window_end":"21:00","temp_drop_celsius":6}},
        "expected_min": 30
    },

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP B: THIN PAYLOADS — known kinds with missing data
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "B1 — perf_dip with NO delta_pct in payload (core field missing)",
        "category": {"slug":"gyms","voice":{"tone":"motivational, data-driven","vocab_taboo":["lose weight fast"]}},
        "merchant": {"identity":{"name":"FitZone Gym","owner_first_name":"Karan","locality":"Powai","languages":["English"]},
                     "performance":{"views":1800,"calls":44,"ctr":2.4},"signals":[],"offers":[{"title":"3-month membership ₹2999","status":"active"}]},
        "trigger": {"kind":"perf_dip","urgency":"high",
                    "payload":{"reason":"traffic_drop"}},  # no delta_pct — thin
        "expected_min": 25
    },
    {
        "label": "B2 — renewal_due with missing plan name and days_remaining",
        "category": {"slug":"dentists","voice":{"tone":"clinical, peer-to-peer","vocab_taboo":["cure","guaranteed","best dentist"]}},
        "merchant": {"identity":{"name":"Smile Dental Clinic","owner_first_name":"Dr. Mehta","locality":"Bandra","languages":["English","Hindi"]},
                     "performance":{"views":720,"calls":18,"ctr":2.5},"signals":[],"offers":[]},
        "trigger": {"kind":"renewal_due","urgency":"high",
                    "payload":{"status":"expiring_soon"}},  # no plan/days
        "expected_min": 22
    },
    {
        "label": "B3 — festival_upcoming with empty trends list",
        "category": {"slug":"restaurants","voice":{"tone":"operator-to-operator","vocab_taboo":[]}},
        "merchant": {"identity":{"name":"Punjabi Dhaba","owner_first_name":"Gurpreet","locality":"Karol Bagh","languages":["Hindi","Punjabi"]},
                     "performance":{"views":5100,"calls":230,"ctr":4.5},"signals":[],"offers":[{"title":"Thali ₹199","status":"active"}]},
        "trigger": {"kind":"festival_upcoming","urgency":"medium",
                    "payload":{"festival_name":"Eid","days_until":3,"trends":[]}},
        "expected_min": 28
    },

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP C: CATEGORY VOICE STRESS TEST
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "C1 — Dentist with perf_dip: must NOT use promotional language",
        "category": {"slug":"dentists","voice":{"tone":"clinical, peer-to-peer","vocab_taboo":["cure","guaranteed","best dentist","discount"]}},
        "merchant": {"identity":{"name":"White Pearl Dental","owner_first_name":"Dr. Sharma","locality":"Civil Lines Delhi","languages":["Hindi","English"]},
                     "performance":{"views":640,"calls":14,"ctr":2.2},"signals":["high_risk_patients: 87"],"offers":[]},
        "trigger": {"kind":"perf_dip","urgency":"high",
                    "payload":{"delta_pct":-31,"metric":"calls","period_days":30,"peer_avg_calls":22}},
        "expected_min": 35
    },
    {
        "label": "C2 — Gym with regulation_change: compliance tone must still be motivational",
        "category": {"slug":"gyms","voice":{"tone":"motivational, member-focused","vocab_taboo":["lose weight fast","guaranteed results"]}},
        "merchant": {"identity":{"name":"Iron Temple Gym","owner_first_name":"Rohit","locality":"Andheri West","languages":["English","Hindi"]},
                     "performance":{"views":2200,"calls":88,"ctr":4.0},"signals":[],"offers":[{"title":"6-month ₹6999","status":"active"}]},
        "trigger": {"kind":"regulation_change","urgency":"critical",
                    "payload":{"regulation_title":"FSSAI Supplement Labelling Update 2026",
                               "compliance_deadline":"2026-05-15","non_compliance_fine":25000,
                               "items_affected":12}},
        "expected_min": 30
    },
    {
        "label": "C3 — Pharmacy with ipl_match_today: must not use sports hype; keep clinical",
        "category": {"slug":"pharmacies","voice":{"tone":"trustworthy, utility-focused","vocab_taboo":["miracle","cure all"]}},
        "merchant": {"identity":{"name":"Wellness Pharmacy","owner_first_name":"Anita","locality":"Thane","languages":["Marathi","English"]},
                     "performance":{"views":1100,"calls":32,"ctr":2.9},"signals":[],"offers":[{"title":"ORS Pack ₹25","status":"active"}]},
        "trigger": {"kind":"ipl_match_today","urgency":"high",
                    "payload":{"team":"Mumbai Indians","match_time":"19:30",
                               "predicted_demand_uplift":41,"top_skus":["ORS","Paracetamol","energy_drinks"]}},
        "expected_min": 30
    },

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP D: BOILERPLATE & VALIDATOR TRAPS
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "D1 — Known kind but merchant has ZERO active offers and no signals",
        "category": {"slug":"salons","voice":{"tone":"warm, aspirational","vocab_taboo":["cheap","discount salon"]}},
        "merchant": {"identity":{"name":"Trendz Salon","owner_first_name":"Sunita","locality":"Vasant Kunj","languages":["Hindi"]},
                     "performance":{"views":310,"calls":4,"ctr":1.3},"signals":[],"offers":[]},
        "trigger": {"kind":"perf_dip","urgency":"high",
                    "payload":{"delta_pct":-44,"metric":"views","period_days":14}},
        "expected_min": 28
    },
    {
        "label": "D2 — curious_ask_due: must include views/calls numbers, not generic question",
        "category": {"slug":"restaurants","voice":{"tone":"operator-to-operator","vocab_taboo":[]}},
        "merchant": {"identity":{"name":"Spice Route","owner_first_name":"Farhan","locality":"Connaught Place","languages":["Hindi","English"]},
                     "performance":{"views":3800,"calls":102,"ctr":2.7},"signals":["lapsed_customers: 34"],"offers":[{"title":"Lunch combo ₹299","status":"active"}]},
        "trigger": {"kind":"curious_ask_due","urgency":"low","payload":{}},
        "expected_min": 28
    },
    {
        "label": "D3 — dormant_with_vera: lapsed customers + retention must appear as numbers",
        "category": {"slug":"gyms","voice":{"tone":"motivational, data-driven","vocab_taboo":[]}},
        "merchant": {"identity":{"name":"Pulse Fitness","owner_first_name":"Vikram","locality":"Whitefield","languages":["English"]},
                     "performance":{"views":1600,"calls":28,"ctr":1.8},"signals":["lapsed_customers: 67","retention_6mo: 0.41"],"offers":[]},
        "trigger": {"kind":"dormant_with_vera","urgency":"medium",
                    "payload":{"days_inactive":45,"lapsed_customers":67,"retention_6mo":0.41}},
        "expected_min": 32
    },

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP E: REPLAY / REPLY SCENARIOS  (tested via /v1/reply)
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "E1 — Merchant gives commitment after outreach",
        "type": "reply",
        "merchant_id_key": "first",
        "conv_id": "conv_adv_e1",
        "message": "Haan bhai, karte hain. Next step kya hai?",
        "turn": 2,
        "expected_action_contains": ["send"],
        "should_NOT_contain": ["would you","do you want","are you sure"],
    },
    {
        "label": "E2 — Hostile opt-out in Hindi",
        "type": "reply",
        "merchant_id_key": "first",
        "conv_id": "conv_adv_e2",
        "message": "Band karo ye sab. Mujhe koi message mat bhejo.",
        "turn": 2,
        "expected_action_contains": ["end","wait"],
        "hostile": True,
    },
    {
        "label": "E3 — Off-topic personal message",
        "type": "reply",
        "merchant_id_key": "first",
        "conv_id": "conv_adv_e3",
        "message": "Kal mera birthday hai, party plan kar raha hoon.",
        "turn": 2,
        "expected_action_contains": ["end","wait","send"],
        "off_topic": True,
    },
    {
        "label": "E4 — Sustained auto-reply loop (5 identical messages)",
        "type": "auto_loop",
        "merchant_id_key": "first",
        "conv_id": "conv_adv_loop",
        "message": "Thank you! Our team will get back to you within 24 hours.",
        "turns": 5,
        "must_end_by_turn": 3,
    },
    {
        "label": "E5 — Merchant asks unrelated question mid-conversation",
        "type": "reply",
        "merchant_id_key": "first",
        "conv_id": "conv_adv_e5",
        "message": "Bhai, tum magicpin mein kaise apply karte hain? Mujhe naukri chahiye.",
        "turn": 3,
        "expected_action_contains": ["end","wait"],
        "off_topic": True,
    },

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP F: ADAPTIVE INJECTION — mid-test NEW payload fields
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "F1 — perf_dip with unexpected new field: anomaly_confidence",
        "category": {"slug":"dentists","voice":{"tone":"clinical, peer-to-peer","vocab_taboo":["cure","guaranteed"]}},
        "merchant": {"identity":{"name":"Care32 Dental","owner_first_name":"Dr. Kapoor","locality":"Pitampura","languages":["Hindi"]},
                     "performance":{"views":810,"calls":19,"ctr":2.3},"signals":[],"offers":[]},
        "trigger": {"kind":"perf_dip","urgency":"high",
                    "payload":{"delta_pct":-27,"metric":"calls","period_days":30,
                               "anomaly_confidence":0.94,          # new injected field
                               "predicted_loss_patients":11}},      # another new field
        "expected_min": 35,
        "note": "Bot must use anomaly_confidence and/or predicted_loss_patients in output"
    },
    {
        "label": "F2 — festival_upcoming with injected social_proof field",
        "category": {"slug":"salons","voice":{"tone":"warm, aspirational","vocab_taboo":["cheap"]}},
        "merchant": {"identity":{"name":"Aura Salon","owner_first_name":"Meena","locality":"Koramangala","languages":["English","Kannada"]},
                     "performance":{"views":1900,"calls":55,"ctr":2.9},"signals":[],"offers":[{"title":"Festival Glow Package ₹1499","status":"active"}]},
        "trigger": {"kind":"festival_upcoming","urgency":"high",
                    "payload":{"festival_name":"Onam","days_until":4,
                               "peer_bookings_this_week":43,    # injected social proof
                               "your_bookings_this_week":7,     # injected for contrast
                               "demand_multiplier":2.1}},
        "expected_min": 35,
        "note": "Must use peer_bookings vs your_bookings as social proof"
    },
    {
        "label": "F3 — regulation_change with injected fine_amount and items_non_compliant",
        "category": {"slug":"pharmacies","voice":{"tone":"trustworthy, compliance-aware","vocab_taboo":["miracle"]}},
        "merchant": {"identity":{"name":"CureWell Pharmacy","owner_first_name":"Suresh","locality":"Sector 62 Noida","languages":["Hindi"]},"performance":{"views":870,"calls":24,"ctr":2.8},"signals":[],"offers":[]},
        "trigger": {"kind":"regulation_change","urgency":"critical",
                    "payload":{"regulation_title":"Drug Pricing Control Order Amendment 2026",
                               "deadline":"2026-05-10","items_non_compliant":8,
                               "fine_amount":50000,"grace_period_days":7}},
        "expected_min": 38,
        "note": "Must cite fine_amount (₹50000) and items_non_compliant (8)"
    },

    # ──────────────────────────────────────────────────────────────────────────
    # GROUP G: STRESS — high concurrency triggers in single tick
    # ──────────────────────────────────────────────────────────────────────────
    {
        "label": "G1 — Tick with 8 triggers simultaneously (latency + quality check)",
        "type": "batch_tick",
        "trigger_ids_count": 8,
        "expected_actions_min": 1,
        "expected_latency_max_ms": 30000
    },
    {
        "label": "G2 — Multiple novel triggers in a single tick (adaptive injection burst)",
        "type": "multi_novel_tick",
        "novel_triggers": [
            {"id":"nov_t1","kind":"market_share_shift","urgency":"high",
             "payload":{"your_share_pct":12.3,"prev_share_pct":15.1,"top_competitor":"Zomato Gold","period_days":30}},
            {"id":"nov_t2","kind":"influencer_mention","urgency":"medium",
             "payload":{"influencer_handle":"@foodie_delhi","reach":84000,"sentiment":"positive","post_date":"2026-05-01"}},
            {"id":"nov_t3","kind":"supply_chain_risk","urgency":"critical",
             "payload":{"affected_items":5,"supplier":"SpiceRoute Ltd","eta_days":14,"stockout_risk_pct":78}},
        ],
        "merchant_category": "restaurants",
    },
]

# =============================================================================
# MAIN ADVERSARIAL JUDGE
# =============================================================================

class AdversarialJudge:
    def __init__(self, llm):
        self.llm     = llm
        self.client  = BotClient(BOT_URL)
        self.scorer  = LLMScorer(llm)
        self.results: List[ScoreResult] = []
        self.reply_results: List[Dict]  = []

    def run(self, scenario="adversarial") -> bool:
        print_header("VERA ADVERSARIAL JUDGE — Real-Judge Stress Test")
        print_info(f"Bot: {BOT_URL}")
        print_info(f"LLM: {self.llm.name()}")

        # Warmup
        if not self._warmup(): return False

        # Load seed dataset
        dataset = DatasetLoader(DATASET_DIR)
        dataset.load()
        self.dataset = dataset

        merchant_ids = list(dataset.merchants.keys())
        first_mid    = merchant_ids[0] if merchant_ids else "m_test_001"

        # Run all cases
        tick_cases  = [c for c in ADVERSARIAL_CASES if c.get("type","tick") == "tick"]
        reply_cases = [c for c in ADVERSARIAL_CASES if c.get("type") == "reply"]
        loop_cases  = [c for c in ADVERSARIAL_CASES if c.get("type") == "auto_loop"]
        batch_cases = [c for c in ADVERSARIAL_CASES if c.get("type") == "batch_tick"]
        novel_cases = [c for c in ADVERSARIAL_CASES if c.get("type") == "multi_novel_tick"]

        print_section(f"TICK CASES — {len(tick_cases)} adversarial triggers")
        for case in tick_cases:
            self._run_tick_case(case, first_mid)

        print_section(f"REPLY / CONVERSATION CASES — {len(reply_cases)+len(loop_cases)} cases")
        for case in reply_cases:
            mid = first_mid
            self._run_reply_case(case, mid)
        for case in loop_cases:
            self._run_loop_case(case, first_mid)

        print_section(f"BATCH TICK CASES — {len(batch_cases)} stress tests")
        for case in batch_cases:
            self._run_batch_tick(case, dataset)

        print_section(f"MULTI-NOVEL TICK — {len(novel_cases)} adaptive injection bursts")
        for case in novel_cases:
            self._run_multi_novel_tick(case, dataset, first_mid)

        self._final_summary()
        return True

    # ─── warmup ───────────────────────────────────────────────────────────────
    def _warmup(self) -> bool:
        print_section("WARMUP")
        data, err, lat = self.client.healthz()
        if err: print_fail(f"healthz: {err}"); return False
        print_success(f"healthz ({lat:.0f}ms)")
        data, err, _ = self.client.metadata()
        if not err:
            print_success(f"metadata — team: {data.get('team_name','?')} model: {data.get('model','?')}")
        return True

    # ─── tick case ────────────────────────────────────────────────────────────
    def _run_tick_case(self, case: Dict, default_mid: str):
        label = case["label"]
        print_section(label)

        # Push merchant context
        mid = f"adv_{label[:20].replace(' ','_').lower()}"
        merchant = case["merchant"]
        merchant.setdefault("merchant_id", mid)
        self.client.push_context("merchant", mid, 1, merchant)

        # Push category context
        cat = case["category"]
        slug = cat["slug"]
        self.client.push_context("category", slug, 1, cat)

        # Push trigger context
        tid = f"adv_t_{label[:15].replace(' ','_').lower()}"
        trigger = {**case["trigger"], "id": tid,
                   "merchant_id": mid, "scope": "merchant",
                   "suppression_key": f"adv_{tid}",
                   "expires_at": "2099-01-01T00:00:00Z"}
        self.client.push_context("trigger", tid, 1, trigger)

        # Tick
        data, err, lat = self.client.tick([tid])
        if err:
            print_fail(f"Tick error: {err}")
            return

        actions = data.get("actions", [])
        print_info(f"Bot returned {len(actions)} action(s) ({lat:.0f}ms)")

        if not actions:
            print_warn("No actions returned — bot chose to skip")
            if case.get("note"):
                print_info(f"Note: {case['note']}")
            return

        for action in actions:
            action["merchant_id"]  = action.get("merchant_id", mid)
            action["trigger_id"]   = action.get("trigger_id", tid)
            score = self.scorer.score(action, cat, merchant, trigger, label=label)
            self.results.append(score)
            self._display_score(score, action, verbose=True)
            exp = case.get("expected_min", 0)
            if score.total < exp:
                print_fail(f"BELOW EXPECTED MIN ({exp}) — got {score.total}/50")
            else:
                print_success(f"Met or exceeded expected minimum {exp}/50")

    # ─── reply case ───────────────────────────────────────────────────────────
    def _run_reply_case(self, case: Dict, mid: str):
        label = case["label"]
        print_section(label)

        data, err, _ = self.client.reply(case["conv_id"], mid, case["message"], case["turn"])

        if err:
            print_fail(f"Reply error: {err}")
            return

        action = data.get("action","?")
        body   = data.get("body","")

        print_info(f"Bot action: {action}")
        if body:
            print_info(f"Body: \"{body[:120]}{'...' if len(body)>120 else ''}\"")

        result = {"label": label, "action": action, "body": body, "passed": False}

        expected = case.get("expected_action_contains", [])
        should_not = case.get("should_NOT_contain", [])

        if expected and action not in expected:
            print_fail(f"Expected action in {expected}, got '{action}'")
        elif should_not and any(w in body.lower() for w in should_not):
            print_fail(f"Body contains disallowed phrase from {should_not}")
        else:
            print_success(f"Action '{action}' is acceptable")
            result["passed"] = True

        if case.get("hostile") and action in ["end","wait"]:
            print_success("Correctly handled hostile message")
        if case.get("off_topic") and action in ["end","wait"]:
            print_success("Correctly handled off-topic message")

        self.reply_results.append(result)

    # ─── auto loop ────────────────────────────────────────────────────────────
    def _run_loop_case(self, case: Dict, mid: str):
        label = case["label"]
        print_section(label)
        ended_at = None

        for i in range(1, case["turns"]+1):
            data, err, _ = self.client.reply(case["conv_id"], mid, case["message"], i+1)
            if err:
                print_fail(f"Turn {i}: {err}")
                return
            action = data.get("action","?")
            if action == "end":
                ended_at = i
                print_success(f"Turn {i}: Bot ENDED — loop detected!")
                break
            elif action == "wait":
                print_warn(f"Turn {i}: Bot WAITING")
            else:
                print_warn(f"Turn {i}: Bot sent: \"{data.get('body','')[:60]}...\"")

        must_end = case.get("must_end_by_turn", 3)
        if ended_at and ended_at <= must_end:
            print_success(f"Loop ended by turn {ended_at} (≤ {must_end} required)")
            self.reply_results.append({"label":label,"passed":True})
        else:
            print_fail(f"Bot did not end loop by turn {must_end}")
            self.reply_results.append({"label":label,"passed":False})

    # ─── batch tick ───────────────────────────────────────────────────────────
    def _run_batch_tick(self, case: Dict, dataset):
        label = case["label"]
        print_section(label)

        # Push all available triggers
        tids = list(dataset.triggers.keys())[:case.get("trigger_ids_count",8)]
        for tid in tids:
            self.client.push_context("trigger", tid, 1, dataset.triggers[tid])
        for mid, m in dataset.merchants.items():
            self.client.push_context("merchant", mid, 1, m)

        data, err, lat = self.client.tick(tids)
        if err:
            print_fail(f"Batch tick error: {err}"); return

        actions  = data.get("actions",[])
        max_lat  = case.get("expected_latency_max_ms", 30000)
        min_acts = case.get("expected_actions_min", 1)

        print_info(f"{len(actions)} actions returned in {lat:.0f}ms")

        if lat > max_lat:
            print_fail(f"Latency {lat:.0f}ms > {max_lat}ms limit")
        else:
            print_success(f"Latency OK ({lat:.0f}ms)")

        if len(actions) < min_acts:
            print_fail(f"Only {len(actions)} actions, expected ≥{min_acts}")
        else:
            print_success(f"Action count OK ({len(actions)})")

    # ─── multi-novel tick ─────────────────────────────────────────────────────
    def _run_multi_novel_tick(self, case: Dict, dataset, first_mid: str):
        label = case["label"]
        print_section(label)
        slug = case.get("merchant_category","restaurants")

        # Pick a real merchant in that category (or fallback)
        mid = first_mid
        for k,m in dataset.merchants.items():
            if m.get("category_slug","") == slug:
                mid = k; break

        self.client.push_context("merchant", mid, 1, dataset.merchants.get(mid,{}))

        novel_triggers = case["novel_triggers"]
        tids = []
        for t in novel_triggers:
            t_payload = {**t, "merchant_id": mid, "scope":"merchant",
                         "suppression_key": f"adv_{t['id']}",
                         "expires_at": "2099-01-01T00:00:00Z"}
            self.client.push_context("trigger", t["id"], 1, t_payload)
            tids.append(t["id"])

        data, err, lat = self.client.tick(tids)
        if err:
            print_fail(f"Tick error: {err}"); return

        actions = data.get("actions",[])
        print_info(f"{len(actions)} actions from {len(tids)} novel triggers ({lat:.0f}ms)")

        merchant = dataset.merchants.get(mid,{})
        cat = dataset.categories.get(slug,{"slug":slug,"voice":{"tone":"operator","vocab_taboo":[]}})

        for action in actions:
            tid = action.get("trigger_id","")
            trigger = next((t for t in novel_triggers if t["id"]==tid),
                           {"kind":"unknown","urgency":"medium","payload":{}})
            score = self.scorer.score(action, cat, merchant, trigger, label=f"{label} [{tid}]")
            self.results.append(score)
            self._display_score(score, action, verbose=True)

    # ─── display ──────────────────────────────────────────────────────────────
    def _display_score(self, score: ScoreResult, action: Dict, verbose=True):
        body = action.get("body","")[:60]
        print(f"\n{Colors.CYAN}Message:{Colors.RESET} \"{body}...\"")
        print_score_bar("Specificity",    score.specificity)
        if verbose and score.specificity_reason:    print_reason(score.specificity_reason)
        print_score_bar("Category Fit",   score.category_fit)
        if verbose and score.category_fit_reason:   print_reason(score.category_fit_reason)
        print_score_bar("Merchant Fit",   score.merchant_fit)
        if verbose and score.merchant_fit_reason:   print_reason(score.merchant_fit_reason)
        print_score_bar("Decision Quality", score.decision_quality)
        if verbose and score.decision_quality_reason: print_reason(score.decision_quality_reason)
        print_score_bar("Engagement",     score.engagement_compulsion)
        if verbose and score.engagement_reason:     print_reason(score.engagement_reason)
        if score.penalties:
            print(f"  {Colors.RED}Penalties: -{score.penalties}{Colors.RESET}")
            for r in score.penalty_reasons: print_reason(r)
        print(f"\n  {Colors.BOLD}TOTAL: {score.total}/50{Colors.RESET}")
        if verbose and score.hint: print_hint(score.hint)

    # ─── final summary ────────────────────────────────────────────────────────
    def _final_summary(self):
        print_section("FINAL ADVERSARIAL SUMMARY")

        # Tick scores
        if self.results:
            n   = len(self.results)
            avg = lambda f: sum(getattr(s,f) for s in self.results) // n
            print_info(f"Scored tick messages: {n}")
            print_score_bar("Avg Specificity",     avg("specificity"))
            print_score_bar("Avg Category Fit",    avg("category_fit"))
            print_score_bar("Avg Merchant Fit",    avg("merchant_fit"))
            print_score_bar("Avg Decision Quality",avg("decision_quality"))
            print_score_bar("Avg Engagement",      avg("engagement_compulsion"))
            total_avg = sum(s.total for s in self.results) // n
            pct = (total_avg / 50) * 100
            print(f"\n  {Colors.BOLD}AVG SCORE (ADVERSARIAL): {total_avg}/50 ({pct:.0f}%){Colors.RESET}")

            # Breakdown by group
            groups = {"A — Novel triggers":[], "B — Thin payloads":[],
                      "C — Category voice":[], "D — Validator traps":[],
                      "F — Adaptive injection":[], "G — Batch/Novel tick":[]}
            for s in self.results:
                for g in groups:
                    if s.case_label.startswith(g[0]):
                        groups[g].append(s.total); break
            print()
            for g, scores in groups.items():
                if scores:
                    gavg = sum(scores) // len(scores)
                    color = Colors.GREEN if gavg >= 35 else Colors.YELLOW if gavg >= 25 else Colors.RED
                    print(f"  {color}{g}: avg {gavg}/50 over {len(scores)} msgs{Colors.RESET}")

        # Reply scores
        if self.reply_results:
            passed = sum(1 for r in self.reply_results if r.get("passed"))
            total  = len(self.reply_results)
            print(f"\n  Reply/conv tests: {passed}/{total} passed")
            for r in self.reply_results:
                label = r.get("label","")
                (print_success if r.get("passed") else print_fail)(label)

        # Verdict
        if self.results:
            if pct >= 80:  print(f"\n  {Colors.GREEN}REAL-JUDGE READY ✓{Colors.RESET}")
            elif pct >= 60: print(f"\n  {Colors.YELLOW}COMPETITIVE — minor fixes needed{Colors.RESET}")
            elif pct >= 40: print(f"\n  {Colors.YELLOW}VULNERABLE — adaptive injection will hurt{Colors.RESET}")
            else:           print(f"\n  {Colors.RED}HIGH RISK — real judge will score lower than simulator{Colors.RESET}")

# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    print_header("Vera Adversarial Judge")
    if LLM_PROVIDER != "ollama" and not LLM_API_KEY:
        print_fail("LLM_API_KEY not set"); sys.exit(1)
    try:
        llm = create_provider()
        print_info(f"LLM: {llm.name()}")
    except Exception as e:
        print_fail(f"Provider error: {e}"); sys.exit(1)

    print_info("Testing LLM connection...")
    try:
        r = llm.complete("Reply 'ready'.", "You are a test assistant.")
        if r: print_success("LLM connected")
        else: print_fail("LLM empty response"); sys.exit(1)
    except Exception as e:
        print_fail(f"LLM failed: {e}"); sys.exit(1)

    judge = AdversarialJudge(llm)
    judge.run(TEST_SCENARIO)

if __name__ == "__main__":
    main()
