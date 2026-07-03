#!/usr/bin/env python3
"""
Vera Bot Endpoint Validation — Sync Version
=============================================
Test bot outputs against case-study gold standards.
No async, direct HTTP calls using requests library.
"""

import json
import sys
import time

try:
    import requests
except ImportError:
    print("❌ Missing 'requests' library. Install: pip install requests")
    sys.exit(1)

BOT_URL = "https://kkalra-vera-magicpin.hf.space"

# Case-study inputs + expected outputs
CASES = [
    {
        "id": 1,
        "name": "Dentists / Research Digest (merchant)",
        "payload": {
            "context_id": "case_1_drmeera",
            "conv_id": "conv_case1_research_digest",
            "trigger_kind": "research_digest",
            "customer_name": None,
            "scope": "merchant"
        },
        "expected_signals": [
            "JIDA", "meera", "2100", "38", "fluoride", "draft", "want"
        ],
        "gold_snippet": "Dr. Meera, JIDA's Oct issue landed...specific 2,100-patient trial...38% better",
    },
    {
        "id": 2,
        "name": "Dentists / Recall Reminder (customer)",
        "payload": {
            "context_id": "case_2_priya",
            "conv_id": "conv_case2_recall_due",
            "trigger_kind": "recall_due",
            "customer_name": "Priya",
            "scope": "customer"
        },
        "expected_signals": [
            "priya", "nov", "wed", "thu", "299", "fluoride", "reply", "recall"
        ],
        "gold_snippet": "Hi Priya...6-month cleaning recall is due...Wed 5 Nov, 6pm ya Thu 6 Nov, 5pm...₹299",
    },
    {
        "id": 3,
        "name": "Salons / Bridal Followup (customer)",
        "payload": {
            "context_id": "case_3_kavya",
            "conv_id": "conv_case3_bridal",
            "trigger_kind": "bridal_followup",
            "customer_name": "Kavya",
            "scope": "customer"
        },
        "expected_signals": [
            "kavya", "wedding", "196", "days", "skin", "program", "saturday", "slot"
        ],
        "gold_snippet": "Hi Kavya 💍 Lakshmi from Studio11...196 days to your wedding",
    },
    {
        "id": 5,
        "name": "Restaurants / IPL Match (merchant)",
        "payload": {
            "context_id": "case_5_ipl",
            "conv_id": "conv_case5_ipl",
            "trigger_kind": "ipl_match_today",
            "customer_name": None,
            "scope": "merchant"
        },
        "expected_signals": [
            "suresh", "dc", "mi", "12%", "bogo", "pizza", "delivery", "swiggy", "insta"
        ],
        "gold_snippet": "Quick heads-up Suresh — DC vs MI...Saturday IPL matches usually shift -12% restaurant covers",
    },
]


def health_check(url):
    """Check if bot endpoint is alive."""
    try:
        r = requests.get(f"{url}/v1/healthz", timeout=5)
        status = "✅ OK" if r.status_code == 200 else f"⚠️  HTTP {r.status_code}"
        print(f"\n{status} — {url}/v1/healthz")
        return r.status_code == 200
    except Exception as e:
        print(f"\n❌ Cannot reach {url}: {e}")
        return False


def test_case(case_def):
    """Test a single case."""
    
    print(f"\n{'='*80}")
    print(f"📌 Case #{case_def['id']}: {case_def['name']}")
    print(f"{'='*80}")
    
    print(f"\n📋 Payload:")
    print(json.dumps(case_def['payload'], indent=2))
    
    print(f"\n🏆 Gold Standard Snippet:")
    print(f"   {case_def['gold_snippet']}")
    
    print(f"\n📡 Calling {BOT_URL}/v1/tick...")
    
    try:
        start = time.time()
        r = requests.post(
            f"{BOT_URL}/v1/tick",
            json=case_def['payload'],
            timeout=20
        )
        elapsed = time.time() - start
        
        print(f"   Status: {r.status_code} (took {elapsed:.1f}s)")
        
        if r.status_code != 200:
            print(f"   Error: {r.text[:200]}")
            return None
        
        result = r.json()
        bot_msg = result.get("message", "")
        
        print(f"\n🤖 Bot Output ({len(bot_msg)} chars):")
        print(f"   {bot_msg}")
        
        # Signal detection
        print(f"\n✅ Signal Detection:")
        found = 0
        for signal in case_def['expected_signals']:
            present = signal.lower() in bot_msg.lower()
            symbol = "✅" if present else "❌"
            print(f"   {symbol} {signal}")
            if present:
                found += 1
        
        print(f"\n   Score: {found}/{len(case_def['expected_signals'])} signals found")
        
        # Basic checks
        print(f"\n🔧 Format Checks:")
        checks = {
            "Not empty": len(bot_msg.strip()) > 0,
            "Under 320 chars": len(bot_msg) <= 320,
            "No raw URLs": "http://" not in bot_msg and "https://" not in bot_msg,
            "Has valid JSON": len(result.get("message", "")) > 0,
        }
        
        for check, passed in checks.items():
            symbol = "✅" if passed else "❌"
            print(f"   {symbol} {check}")
        
        pass_count = sum(1 for v in checks.values() if v)
        signal_pct = 100 * found / len(case_def['expected_signals'])
        
        print(f"\n📊 Dimension Score: {signal_pct:.0f}% signals + {pass_count}/{len(checks)} format checks")
        
        return {
            "case_id": case_def['id'],
            "message": bot_msg,
            "signals_found": found,
            "signals_total": len(case_def['expected_signals']),
            "format_checks": pass_count,
        }
        
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return None


def main():
    print("\n" + "="*80)
    print("🚀 VERA BOT VALIDATION — Case Study Tests")
    print("="*80)
    print(f"\nBot URL: {BOT_URL}")
    print(f"Test Cases: {len(CASES)}")
    
    # Health check
    print(f"\n1️⃣  HEALTH CHECK")
    print("-" * 80)
    if not health_check(BOT_URL):
        print("\n❌ Bot endpoint is unreachable. Try /v1/healthz endpoint.")
        sys.exit(1)
    
    # Run tests
    print(f"\n2️⃣  CASE VALIDATIONS")
    print("-" * 80)
    
    results = []
    for case in CASES:
        result = test_case(case)
        if result:
            results.append(result)
        time.sleep(1)  # Rate limit
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    
    if not results:
        print("\n❌ No successful cases. Bot may be down.")
        sys.exit(1)
    
    print(f"\n✅ Cases tested: {len(results)}/{len(CASES)}")
    
    total_signals = sum(r['signals_found'] for r in results)
    total_signal_capacity = sum(r['signals_total'] for r in results)
    signal_pct = 100 * total_signals / total_signal_capacity if total_signal_capacity > 0 else 0
    
    print(f"\n📈 Overall Signal Detection: {total_signals}/{total_signal_capacity} ({signal_pct:.1f}%)")
    
    avg_format = sum(r['format_checks'] for r in results) / len(results) if results else 0
    print(f"📝 Avg Format Score: {avg_format:.1f}/4")
    
    print(f"\n💡 Interpretation:")
    if signal_pct >= 80:
        print(f"   ✅ Bot is strong on case-study signals ({signal_pct:.0f}%)")
    elif signal_pct >= 60:
        print(f"   ⚠️  Bot captures most signals ({signal_pct:.0f}%) but some gaps")
    else:
        print(f"   ❌ Bot misses key case-study patterns ({signal_pct:.0f}%)")
    
    print(f"\n🎯 Next Steps:")
    print(f"   1. Run full validation: python validate_case_studies.py")
    print(f"   2. Use judge simulator: cd magicpin-ai-challenge && python judge_simulator.py --scenario full_evaluation")
    print(f"   3. Review bot.py compose() function for dimension gaps")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
