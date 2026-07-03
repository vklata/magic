#!/usr/bin/env python3
"""
Data Access Validator
======================
Checks if bot is actually using dataset context data or falling back to generic templates.

Tests:
1. Are merchant names injected? (owner_first_name)
2. Are specific numbers from context? (not fabricated)
3. Are offers from merchant catalog? (not invented)
4. Are slots from trigger payload? (exact dates)
5. Are customer prefs honored? (language, times)
"""

import json
import requests
import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

BOT_URL = "https://kkalra-vera-magicpin.hf.space"
DATASET_ROOT = Path("magicpin-ai-challenge/dataset")
EXPANDED_ROOT = Path("magicpin-ai-challenge/expanded")

# Test cases: (merchant_id, trigger_id, customer_id, what_to_check)
TEST_CASES = [
    {
        "name": "Dr. Meera + Research Digest",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "trigger_id": "trg_001_research_digest_dentists",
        "customer_id": None,
        "must_have": [
            ("merchant_name", "meera", "Owner first name in message"),
            ("merchant_locality", "lajpat", "Locality mentioned"),
            ("source_citation", "jida", "Research source (JIDA)"),
            ("specific_number", "2100|2,100", "Trial size (2,100 patients)"),
            ("specific_number", "38", "Effect size (38%)"),
        ]
    },
    {
        "name": "Priya + Recall Reminder",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "trigger_id": "trg_003_recall_due_priya",
        "customer_id": "c_001_priya_for_m001",
        "must_have": [
            ("customer_name", "priya", "Customer first name"),
            ("merchant_name", "meera", "Merchant first name"),
            ("offer_price", "299", "Real offer price (₹299)"),
            ("slot_date_wed", "5|nov|5 nov", "Slot date: Wed 5 Nov"),
            ("slot_date_thu", "6|nov|6 nov", "Slot date: Thu 6 Nov"),
            ("language_pref", "apke|liye|hain|ya", "Hindi-English mix (Priya's pref)"),
        ]
    },
    {
        "name": "Kavya + Bridal Followup",
        "merchant_id": "m_003_studio11_salon_hyderabad",
        "trigger_id": "trg_007_bridal_followup_kavya",
        "customer_id": "c_005_kavya_for_m003",
        "must_have": [
            ("customer_name", "kavya", "Customer first name"),
            ("wedding_countdown", "196", "Days to wedding (196)"),
            ("merchant_name", "lakshmi", "Owner first name (Lakshmi)"),
            ("specific_price", "2499|2,499", "Package price (₹2,499)"),
            ("slot_preference", "saturday", "Saturday preference (from pref)"),
        ]
    },
    {
        "name": "Rashmi + Lapse Winback",
        "merchant_id": "m_007_powerhouse_gym_bangalore",
        "trigger_id": "trg_008_lapse_winback_rashmi",
        "customer_id": "c_008_rashmi_for_m007",
        "must_have": [
            ("customer_name", "rashmi", "Customer name"),
            ("merchant_name", "karthik", "Owner first name"),
            ("class_type", "hiit", "Class type (HIIT)"),
            ("class_day", "tue|thu", "Class days (Tue/Thu)"),
            ("class_time", "630|6:30|6.30", "Class time (6:30pm)"),
            ("no_shame_voice", "happens|judgment|no judgment", "No-shame framing"),
        ]
    },
    {
        "name": "Ramesh + Supply Alert",
        "merchant_id": "m_009_apollo_pharmacy_jaipur",
        "trigger_id": "trg_009_supply_alert_atorva",
        "customer_id": None,
        "must_have": [
            ("merchant_name", "ramesh", "Owner first name"),
            ("batch_numbers", "at2024", "Batch numbers (AT2024)"),
            ("affected_count", "22", "Affected customer count (22)"),
            ("total_count", "240", "Total chronic customers (240)"),
            ("risk_framing", "sub-potency|no safety", "Risk-bounded framing"),
        ]
    },
]


def load_context(merchant_id: Optional[str], trigger_id: Optional[str], customer_id: Optional[str]):
    """Load actual context data from dataset."""
    contexts = {}
    
    if merchant_id:
        try:
            merchant_file = EXPANDED_ROOT / "merchants" / f"{merchant_id}.json"
            if not merchant_file.exists():
                merchant_file = DATASET_ROOT / "merchants_seed.json"
            with open(merchant_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    contexts['merchant'] = [m for m in data if m['merchant_id'] == merchant_id][0]
                else:
                    contexts['merchant'] = data
            
            # Also load category context
            category_slug = contexts['merchant'].get('category_slug')
            if category_slug:
                cat_file = EXPANDED_ROOT / "categories" / f"{category_slug}.json"
                if not cat_file.exists():
                    cat_file = DATASET_ROOT / "categories" / f"{category_slug}.json"
                with open(cat_file) as f:
                    contexts['category'] = json.load(f)
        except Exception as e:
            print(f"   ⚠️ Warning: Failed to load merchant/category context: {e}")
    
    if trigger_id:
        try:
            trigger_file = EXPANDED_ROOT / "triggers" / f"{trigger_id}.json"
            if not trigger_file.exists():
                trigger_file = DATASET_ROOT / "triggers_seed.json"
            with open(trigger_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    contexts['trigger'] = [t for t in data if t['id'] == trigger_id][0]
                else:
                    contexts['trigger'] = data
        except Exception as e:
            print(f"   ⚠️ Warning: Failed to load trigger context: {e}")
    
    if customer_id:
        try:
            customer_file = EXPANDED_ROOT / "customers" / f"{customer_id}.json"
            if not customer_file.exists():
                customer_file = DATASET_ROOT / "customers_seed.json"
            with open(customer_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    contexts['customer'] = [c for c in data if c['customer_id'] == customer_id][0]
                else:
                    contexts['customer'] = data
        except Exception as e:
            print(f"   ⚠️ Warning: Failed to load customer context: {e}")
    
    return contexts


def push_to_bot(contexts: dict):
    """Push loaded contexts to the bot's /v1/context endpoint."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    mapping = {
        'merchant': ('merchant', contexts.get('merchant', {}).get('merchant_id')),
        'trigger': ('trigger', contexts.get('trigger', {}).get('id')),
        'customer': ('customer', contexts.get('customer', {}).get('customer_id')),
        'category': ('category', contexts.get('category', {}).get('slug'))
    }
    
    for key, (scope, cid) in mapping.items():
        if not cid or not contexts.get(key):
            continue
        
        payload = {
            "scope": scope,
            "context_id": cid,
            "version": 1,
            "payload": contexts[key],
            "delivered_at": now
        }
        try:
            r = requests.post(f"{BOT_URL}/v1/context", json=payload, timeout=5)
            if r.status_code != 200:
                print(f"   ⚠️ Warning: Failed to push {scope} context ({r.status_code})")
        except Exception as e:
            print(f"   ⚠️ Warning: Error pushing {scope} context: {e}")


def test_case(test_def):
    """Test a single case for data access."""
    
    print(f"\n{'='*80}")
    print(f"📌 {test_def['name']}")
    print(f"{'='*80}")
    
    # Load actual context
    contexts = load_context(
        test_def.get('merchant_id'),
        test_def.get('trigger_id'),
        test_def.get('customer_id')
    )
    
    print(f"\n📦 Context Loaded:")
    if 'merchant' in contexts:
        m = contexts['merchant']
        print(f"   ✓ Merchant: {m.get('identity', {}).get('name')} " 
              f"({m.get('identity', {}).get('owner_first_name')})")
    if 'category' in contexts:
        print(f"   ✓ Category: {contexts['category'].get('slug')}")
    if 'trigger' in contexts:
        t = contexts['trigger']
        print(f"   ✓ Trigger: {t.get('kind')}")
    if 'customer' in contexts:
        c = contexts['customer']
        print(f"   ✓ Customer: {c.get('identity', {}).get('name')}")
    
    # Push context to bot first
    push_to_bot(contexts)
    
    # Call bot via /v1/tick
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trigger_id = test_def.get('trigger_id')
    payload = {
        "now": now_str,
        "available_triggers": [trigger_id] if trigger_id else []
    }
    
    print(f"\n📡 Calling bot...")
    try:
        r = requests.post(f"{BOT_URL}/v1/tick", json=payload, timeout=20)
        if r.status_code != 200:
            print(f"   ❌ Error: {r.status_code}")
            if r.status_code == 422:
                print(f"   📝 Details: {r.text}")
            return None
        
        actions = r.json().get("actions", [])
        if not actions:
            print(f"   ❌ Error: Bot returned no actions for trigger {trigger_id}")
            return None
            
        # Find action for this trigger
        action = next((a for a in actions if a.get('trigger_id') == trigger_id), actions[0])
        message = action.get("body", "")
        print(f"   ✓ Received {len(message)} chars")
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return None
    
    # Validate signals
    print(f"\n✅ Data Access Checks:")
    passed = 0
    failed = []
    
    for signal_type, pattern, description in test_def['must_have']:
        found = check_signal(message, pattern)
        symbol = "✅" if found else "❌"
        print(f"   {symbol} {description}")
        
        if found:
            passed += 1
        else:
            failed.append(f"{signal_type}: {pattern}")
    
    total = len(test_def['must_have'])
    pct = 100 * passed / total if total > 0 else 0
    
    print(f"\n📊 Data Access Score: {passed}/{total} ({pct:.0f}%)")
    
    if failed:
        print(f"\n❌ Missing signals:")
        for fail in failed:
            print(f"   - {fail}")
    
    print(f"\n💬 Message snippet:")
    print(f"   {message[:150]}...")
    
    return {
        "name": test_def['name'],
        "passed": passed,
        "total": total,
        "pct": pct,
        "failed": failed
    }


def main():
    print("\n" + "="*80)
    print("🔍 VERA DATA ACCESS VALIDATOR")
    print("="*80)
    print("\nChecks if bot is using actual dataset context or falling back to generic templates.")
    print(f"Bot URL: {BOT_URL}")
    
    results = []
    for test_case_def in TEST_CASES:
        result = test_case(test_case_def)
        if result:
            results.append(result)
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}\n")
    
    total_passed = sum(r['passed'] for r in results)
    total_checks = sum(r['total'] for r in results)
    overall_pct = 100 * total_passed / total_checks if total_checks > 0 else 0
    
    print(f"Overall Data Access: {total_passed}/{total_checks} ({overall_pct:.0f}%)\n")
    
    for result in results:
        status = "✅" if result['pct'] >= 80 else "⚠️ " if result['pct'] >= 60 else "❌"
        print(f"{status} {result['name']:40s} {result['passed']:2d}/{result['total']:2d} ({result['pct']:5.0f}%)")
    
    print(f"\n💡 Interpretation:")
    if overall_pct >= 90:
        print(f"   🟢 Excellent — Bot is using actual dataset context effectively")
    elif overall_pct >= 70:
        print(f"   🟡 Good — Most context data being used, minor gaps")
    elif overall_pct >= 50:
        print(f"   🟠 Fair — Some context data used, some generic fallback")
    else:
        print(f"   🔴 Weak — Bot is mostly generic, not accessing dataset properly")
    
    print(f"\n🎯 What data bot should inject per message:")
    print(f"   1. Merchant owner first name (from merchant.identity.owner_first_name)")
    print(f"   2. Specific numbers (from merchant.performance, trigger.payload, category.digest)")
    print(f"   3. Real offers (from merchant.offers[active])")
    print(f"   4. Actual slots/dates (from trigger.payload.available_slots)")
    print(f"   5. Customer prefs (language_pref, preferred_slots from customer context)")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
