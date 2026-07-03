#!/usr/bin/env python3
"""Quick endpoint health check + Case #1 manual validation."""

import httpx
import json
import asyncio

BOT_URL = "https://kkalra-vera-magicpin.hf.space"
LOCAL_BOT = "http://localhost:8080"


async def health_check(url: str):
    """Check if bot is alive."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{url}/v1/healthz")
            print(f"✅ {url} is alive (status {r.status_code})")
            return r.status_code == 200
        except Exception as e:
            print(f"❌ {url} failed: {e}")
            return False


async def test_case_1():
    """Test Case #1: dentists / research_digest (merchant-facing)."""
    
    print("\n" + "="*80)
    print("TEST: Case #1 — Dentists / Research Digest")
    print("="*80)
    
    print("\n📋 Input:")
    print("  Category: dentists")
    print("  Merchant: Dr. Meera (Lajpat Nagar Delhi)")
    print("  Trigger: research_digest (JIDA Oct 2026 paper)")
    print("  Customer: None (merchant-facing)")
    
    print("\n💰 Expected Signals (Case Study Gold):")
    print("  ✓ Source citation (JIDA p.14)")
    print("  ✓ Merchant first name (Dr. Meera)")
    print("  ✓ Specific numbers (2,100 patients, 38%)")
    print("  ✓ Cohort anchor (high-risk adults)")
    print("  ✓ Reciprocity offer (I'll pull it for you)")
    print("  ✓ Binary CTA (Want me to...?)")
    print("  ✓ Length ~170 chars (not >320)")
    
    payload = {
        "context_id": "case_1_drmeera_dentalclinic",
        "conv_id": "conv_case1_research_digest",
        "trigger_kind": "research_digest",
        "customer_name": None,
        "scope": "merchant"
    }
    
    print("\n🔧 Payload:")
    print(json.dumps(payload, indent=2))
    
    print(f"\n📡 Calling {BOT_URL}/v1/tick...")
    
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.post(f"{BOT_URL}/v1/tick", json=payload)
            print(f"   Status: {r.status_code}")
            
            if r.status_code == 200:
                result = r.json()
                bot_msg = result.get("message", "")
                
                print("\n🤖 Bot Output:")
                print(f"   {bot_msg}")
                print(f"   Length: {len(bot_msg)} chars")
                
                print("\n🔍 Quick Validation:")
                checks = {
                    "Has merchant name (Meera)": "meera" in bot_msg.lower(),
                    "Has JIDA citation": "jida" in bot_msg.lower(),
                    "Has 2,100 or 2100": "2100" in bot_msg or "2,100" in bot_msg,
                    "Has 38%": "38" in bot_msg,
                    "Has 'fluoride'": "fluoride" in bot_msg.lower(),
                    "Has binary CTA (Want/Draft)": "want" in bot_msg.lower() or "draft" in bot_msg.lower(),
                    "Under 320 chars": len(bot_msg) <= 320,
                    "Not empty": len(bot_msg.strip()) > 0,
                }
                
                for check, result in checks.items():
                    symbol = "✅" if result else "❌"
                    print(f"   {symbol} {check}")
                
                pass_count = sum(1 for v in checks.values() if v)
                print(f"\n   Score: {pass_count}/{len(checks)} checks passed")
                
                return bot_msg
            else:
                print(f"   Error: {r.text}")
                return None
        except Exception as e:
            print(f"   Exception: {e}")
            return None


async def test_case_2():
    """Test Case #2: dentists / recall_due (customer-facing)."""
    
    print("\n" + "="*80)
    print("TEST: Case #2 — Dentists / Recall Reminder (Customer)")
    print("="*80)
    
    print("\n📋 Input:")
    print("  Category: dentists")
    print("  Merchant: Dr. Meera")
    print("  Trigger: recall_due")
    print("  Customer: Priya (5mo lapsed, weekday evening pref)")
    
    print("\n💰 Expected Signals:")
    print("  ✓ Language mix (Hindi-English)")
    print("  ✓ Specific dates + times (Wed 5 Nov 6pm, etc)")
    print("  ✓ Real price (₹299)")
    print("  ✓ Free add-on (complimentary fluoride)")
    print("  ✓ Multi-choice CTA (Reply 1 for Wed, 2 for Thu)")
    print("  ✓ Recall window explicit (6-month)")
    
    payload = {
        "context_id": "case_2_drmeera_dentalclinic",
        "conv_id": "conv_case2_recall_due",
        "trigger_kind": "recall_due",
        "customer_name": "Priya",
        "scope": "customer"
    }
    
    print(f"\n📡 Calling {BOT_URL}/v1/tick...")
    
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.post(f"{BOT_URL}/v1/tick", json=payload)
            print(f"   Status: {r.status_code}")
            
            if r.status_code == 200:
                result = r.json()
                bot_msg = result.get("message", "")
                
                print("\n🤖 Bot Output:")
                print(f"   {bot_msg}")
                
                print("\n🔍 Quick Validation:")
                checks = {
                    "Has customer name (Priya)": "priya" in bot_msg.lower(),
                    "Has date (Nov, Wed, Thu)": any(x in bot_msg.lower() for x in ["nov", "wed", "thu"]),
                    "Has price (₹299 or 299)": "₹299" in bot_msg or "299" in bot_msg,
                    "Has fluoride": "fluoride" in bot_msg.lower(),
                    "Has Hindi-English mix": any(x in bot_msg for x in ["aapke", "apke", "liye", "hain", "ya"]),
                    "Has CTA (Reply 1/2 or choice)": any(x in bot_msg.lower() for x in ["reply", "1", "2", "tell us"]),
                    "Under 320 chars": len(bot_msg) <= 320,
                }
                
                for check, result in checks.items():
                    symbol = "✅" if result else "❌"
                    print(f"   {symbol} {check}")
                
                pass_count = sum(1 for v in checks.values() if v)
                print(f"\n   Score: {pass_count}/{len(checks)} checks passed")
                
                return bot_msg
            else:
                print(f"   Error: {r.text}")
                return None
        except Exception as e:
            print(f"   Exception: {e}")
            return None


async def main():
    print("\n" + "="*80)
    print("🚀 Vera Bot Endpoint Validation")
    print("="*80)
    
    # Check health
    print("\n1️⃣  Health Check")
    print("-" * 80)
    hosted_ok = await health_check(BOT_URL)
    
    # For local testing, don't fail if local is down
    print(f"   (Local bot at {LOCAL_BOT}: skipped in this run)")
    
    if not hosted_ok:
        print("\n❌ Hosted bot is down. Cannot proceed with tests.")
        return
    
    # Run case tests
    print("\n2️⃣  Case Study Validation")
    print("-" * 80)
    
    case1_msg = await test_case_1()
    case2_msg = await test_case_2()
    
    # Summary
    print("\n" + "="*80)
    print("📊 Summary")
    print("="*80)
    
    if case1_msg and case2_msg:
        print("\n✅ Both test cases succeeded!")
        print("   Case #1 (merchant-facing): Output received")
        print("   Case #2 (customer-facing): Output received")
        print("\nNext steps:")
        print("   1. Run full validation: python validate_case_studies.py")
        print("   2. Or use judge_simulator: cd magicpin-ai-challenge && python judge_simulator.py")
    else:
        print("\n⚠️  Some tests failed. Check bot endpoint connectivity.")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
