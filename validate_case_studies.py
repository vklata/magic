#!/usr/bin/env python3
"""
Vera Case Studies Validator
============================
Test script that validates bot outputs against 10 case-study gold standards.
Scores bot on 5 dimensions: specificity, category fit, merchant fit, trigger relevance, compulsion.

Usage:
    python validate_case_studies.py [--bot-url https://...] [--local]
"""

import json
import re
import sys
import time
import httpx
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import argparse

# Case studies extracted from case-studies.md
CASE_STUDIES = [
    {
        "case_id": 1,
        "category": "dentists",
        "merchant_name": "Dr. Meera",
        "merchant_locality": "Lajpat Nagar, Delhi",
        "trigger": "research_digest",
        "trigger_detail": "JIDA Oct 2026 paper: 3-month fluoride recall vs 6-month, 38% caries reduction in high-risk adults",
        "customer": None,
        "scope": "merchant",
        "expected_ctr": 2.1,
        "gold_message": "Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult patients — 2,100-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month. Want me to pull it + draft a patient-ed WhatsApp you can share?  — JIDA Oct 2026 p.14",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 10},
        "key_signals": ["source_citation_JIDA", "merchant_first_name", "high_risk_cohort_anchor", "specific_numbers_2100_38pct", "reciprocity_offer", "binary_cta"]
    },
    {
        "case_id": 2,
        "category": "dentists",
        "merchant_name": "Dr. Meera",
        "merchant_locality": "Delhi",
        "trigger": "recall_due",
        "trigger_detail": "Priya's 6-month cleaning recall window opened",
        "customer": "Priya (lapsed_soft, 5mo since visit, weekday evening preference)",
        "scope": "customer",
        "expected_slots": ["Wed 5 Nov 6pm", "Thu 6 Nov 5pm"],
        "gold_message": "Hi Priya, Dr. Meera's clinic here 🦷 It's been 5 months since your last visit — your 6-month cleaning recall is due. Apke liye 2 slots ready hain: Wed 5 Nov, 6pm ya Thu 6 Nov, 5pm. ₹299 cleaning + complimentary fluoride. Reply 1 for Wed, 2 for Thu, or tell us a time that works.",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 9},
        "key_signals": ["language_mix_hien", "specific_dates_times", "real_price", "recall_window_explicit", "multi_choice_cta", "warmth_emoji"]
    },
    {
        "case_id": 3,
        "category": "salons",
        "merchant_name": "Lakshmi",
        "merchant_locality": "Studio11 Kapra, Hyderabad",
        "trigger": "bridal_followup",
        "trigger_detail": "Kavya, bride-to-be (wedding 2026-11-08), did Bridal Trial 5 weeks ago, in skin-prep window now",
        "customer": "Kavya (new state, wedding date, opted in for bridal followup)",
        "scope": "customer",
        "wedding_days_left": 196,
        "gold_message": "Hi Kavya 💍 Lakshmi from Studio11 Kapra here. 196 days to your wedding — perfect window to start the 30-day skin-prep program before serious bridal bookings roll in. ₹2,499 covers 4 sessions + a take-home kit. Want me to block your preferred Saturday 4pm slot for the first session next week?",
        "gold_scores": {"specificity": 10, "category_fit": 9, "merchant_fit": 9, "trigger_relevance": 10, "compulsion": 9},
        "key_signals": ["merchant_first_name", "relationship_continuity_trial", "wedding_countdown", "urgency_framing", "specific_price", "preference_honored", "binary_commit"]
    },
    {
        "case_id": 4,
        "category": "salons",
        "merchant_name": "Lakshmi",
        "merchant_locality": "Studio11, Hyderabad",
        "trigger": "curious_ask_due",
        "trigger_detail": "Weekly 'what's in demand?' cadence",
        "customer": None,
        "scope": "merchant",
        "gold_message": "Hi Lakshmi! Quick check — what service has been most asked-for this week at Studio11? I'll turn the answer into a Google post + a 4-line WhatsApp reply you can use when customers ask about pricing. Takes 5 min.",
        "gold_scores": {"specificity": 8, "category_fit": 9, "merchant_fit": 8, "trigger_relevance": 10, "compulsion": 9},
        "key_signals": ["merchant_first_name", "low_stakes_question", "reciprocity_up_front", "effort_externalization", "5min_anchor"]
    },
    {
        "case_id": 5,
        "category": "restaurants",
        "merchant_name": "Suresh",
        "merchant_locality": "SK Pizza Junction, Sant Nagar, Delhi",
        "trigger": "ipl_match_today",
        "trigger_detail": "DC vs MI at Arun Jaitley Stadium, 7:30pm match today (Sat)",
        "customer": None,
        "scope": "merchant",
        "active_offer": "BOGO pizza Tue-Thu",
        "gold_message": "Quick heads-up Suresh — DC vs MI at Arun Jaitley tonight, 7:30pm. Important: Saturday IPL matches usually shift -12% restaurant covers (people watch at home). Skip the match-night promo today; instead push your BOGO pizza (already active) as a delivery-only Saturday special. Want me to draft the Swiggy banner + an Insta story? Live in 10 min.",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 10},
        "key_signals": ["merchant_first_name", "counter_intuitive_data_12pct", "saves_from_bad_decision", "existing_offer_leverage", "concrete_deliverables", "10min_cap", "operator_voice"]
    },
    {
        "case_id": 6,
        "category": "restaurants",
        "merchant_name": "Suresh",
        "merchant_locality": "Mylari South Indian Cafe, Indiranagar, Bangalore",
        "trigger": "active_planning_intent",
        "trigger_detail": "Merchant asked about corporate-bulk thali package; explicitly said 'yes good idea, what would it look like'",
        "customer": None,
        "scope": "merchant",
        "gold_message": "Suresh, here's a starter version — you can edit:\n\nMylari Corporate Thali — for offices in Indiranagar\n- 10 thalis @ ₹125 each (₹25 off retail) + free delivery\n- 25 thalis @ ₹115 each + 2 free filter coffees\n- 50+: ₹105 each + 1 free dosa platter\n- WhatsApp the day-before by 5pm; we deliver between 12:30-1pm\n\n3 offices in Indiranagar are in your delivery radius (Embassy Tech, RMZ Eco, Sigma Soft). Want me to draft a 3-line WhatsApp to send their facilities managers?",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 9},
        "key_signals": ["complete_drafted_artifact", "tiered_pricing", "concrete_radius_names", "follow_on_offer", "b2b_logic", "named_buildings"]
    },
    {
        "case_id": 7,
        "category": "gyms",
        "merchant_name": "Karthik",
        "merchant_locality": "PowerHouse Fitness, HSR Layout, Bangalore",
        "trigger": "seasonal_perf_dip",
        "trigger_detail": "Views -30% w/w (April seasonal drop), expected April-June low; flagged as not-a-problem",
        "customer": None,
        "scope": "merchant",
        "active_members": 245,
        "gold_message": "Karthik, your views are down 30% this week — but I want to flag this is the normal April-June acquisition lull (every metro gym sees -25 to -35% in this window). Action: skip ad spend now, save it for Sept-Oct when conversion is 2x. For now, focus retention on your 245 members. Want me to draft a 'summer attendance challenge' to keep them through the dip?",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 8},
        "key_signals": ["anxiety_preemption", "data_anchor_25_35pct", "reframe_as_opportunity", "member_count", "action_proposal", "specific_months"]
    },
    {
        "case_id": 8,
        "category": "gyms",
        "merchant_name": "Karthik",
        "merchant_locality": "PowerHouse Fitness, Bangalore",
        "trigger": "customer_lapsed_hard",
        "trigger_detail": "Rashmi, 57 days since last visit, previous focus was weight loss, was 5-month member",
        "customer": "Rashmi (lapsed_hard, weight-loss goal)",
        "scope": "customer",
        "gold_message": "Hi Rashmi 👋 Karthik from PowerHouse here. It's been about 8 weeks — happens to most members at some point, no judgment. We've added a Tue/Thu evening HIIT class that fits weight-loss goals well (45 min, 6:30pm). Want me to hold a free trial spot for you next Tue, 30 Apr? Reply YES — no commitment, no auto-charge.",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 10},
        "key_signals": ["merchant_first_name", "warmth_emoji", "no_shame_framing", "addresses_past_goal", "specific_class_details", "no_commitment_trial", "binary_cta", "removes_barriers"]
    },
    {
        "case_id": 9,
        "category": "pharmacies",
        "merchant_name": "Ramesh",
        "merchant_locality": "Apollo Health Plus Pharmacy, Malviya Nagar, Jaipur",
        "trigger": "supply_alert",
        "trigger_detail": "Voluntary recall on atorvastatin batches AT2024-1102 + AT2024-1108 by Mfr Z — sub-potency, no safety risk",
        "customer": None,
        "scope": "merchant",
        "chronic_customers": 240,
        "affected_customers": 22,
        "gold_message": "Ramesh, urgent: voluntary recall on 2 atorvastatin batches (AT2024-1102, AT2024-1108) by Mfr Z — sub-potency, no safety risk, but customers should be informed for replacement. Pulled your repeat-Rx list: 22 of your chronic-Rx customers were dispensed these batches in last 90 days. Want me to draft their WhatsApp note + the replacement-pickup workflow?",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 10},
        "key_signals": ["merchant_first_name", "batch_numbers", "risk_bounded_framing", "derived_count_22_of_240", "end_to_end_workflow", "source_citation", "urgency"]
    },
    {
        "case_id": 10,
        "category": "pharmacies",
        "merchant_name": "Apollo Health Plus",
        "merchant_locality": "Malviya Nagar, Jaipur",
        "trigger": "chronic_refill_due",
        "trigger_detail": "Mr. Sharma's metformin/atorvastatin/telmisartan run out 2026-04-28",
        "customer": "Mr. Sharma (65-75 age, senior citizen, channel via son's WhatsApp)",
        "scope": "customer",
        "gold_message": "Namaste — Apollo Health Plus Malviya Nagar yahan. Sharma ji ki 3 monthly medicines (metformin, atorvastatin, telmisartan) 28 April ko khatam hongi. Same dose, same brand pack ready hai. Senior discount 15% applied — total ₹1,420 (₹240 saved). Free home delivery to saved address by 5pm tomorrow. Reply CONFIRM to dispatch, or call 9876543210 if any change in dosage.",
        "gold_scores": {"specificity": 10, "category_fit": 10, "merchant_fit": 10, "trigger_relevance": 10, "compulsion": 9},
        "key_signals": ["namaste_salutation", "molecule_names_precise", "specific_date", "total_savings_shown", "two_channel_option", "senior_norms", "trustworthy_voice"]
    }
]


@dataclass
class ScoringResult:
    case_id: int
    bot_message: str
    gold_message: str
    bot_scores: dict
    gold_scores: dict
    gaps: dict  # dimension -> gap (gold - bot)
    signals_found: list
    errors: list


def extract_json_from_llm(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling code blocks."""
    # Try raw JSON first
    try:
        return json.loads(text)
    except:
        pass
    
    # Try markdown code block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    
    return None


async def call_bot(
    bot_url: str,
    case_id: int,
    category: str,
    merchant_name: str,
    trigger_kind: str,
    customer_name: Optional[str] = None
) -> str:
    """Call bot /v1/tick endpoint."""
    
    context_id = f"test_{category}_{merchant_name.replace(' ', '_').lower()}"
    conv_id = f"conv_{case_id}_{int(time.time())}"
    
    # Build payload matching bot's expectations
    payload = {
        "context_id": context_id,
        "conv_id": conv_id,
        "trigger_kind": trigger_kind,
        "customer_name": customer_name or "N/A",
        "scope": "merchant" if not customer_name else "customer"
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{bot_url}/v1/tick",
                json=payload
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("message", "")
            else:
                return f"[Error {resp.status_code}] {resp.text}"
        except Exception as e:
            return f"[Exception] {str(e)}"


def score_dimension(bot_msg: str, gold_msg: str, dimension: str) -> int:
    """Quick heuristic scoring of a dimension (0-10)."""
    
    bot_len = len(bot_msg.strip())
    gold_len = len(gold_msg.strip())
    
    # Length similarity
    if bot_len == 0:
        return 0
    
    length_ratio = min(bot_len, gold_len) / max(bot_len, gold_len)
    
    # Word overlap (simple jaccard)
    bot_words = set(re.findall(r'\w+', bot_msg.lower()))
    gold_words = set(re.findall(r'\w+', gold_msg.lower()))
    
    if len(gold_words) == 0:
        overlap = 0
    else:
        overlap = len(bot_words & gold_words) / len(gold_words)
    
    # Combined score
    combined = (length_ratio * 0.3 + overlap * 0.7) * 10
    
    # Clamp to 0-10
    return max(0, min(10, int(combined)))


def extract_signals(bot_msg: str, expected_signals: list) -> tuple[list, list]:
    """Extract which signals are present in bot message."""
    found = []
    missing = []
    
    for signal in expected_signals:
        # Simple heuristic: check if signal concept appears
        signal_keywords = signal.lower().replace('_', ' ').split()
        
        msg_lower = bot_msg.lower()
        if any(keyword in msg_lower for keyword in signal_keywords):
            found.append(signal)
        else:
            missing.append(signal)
    
    return found, missing


def print_result(result: ScoringResult):
    """Print scored result with visual formatting."""
    print(f"\n{'='*80}")
    print(f"Case #{result.case_id}")
    print(f"{'='*80}")
    
    print(f"\n📌 Gold Standard Message:")
    print(f"  {result.gold_message[:120]}...")
    
    print(f"\n🤖 Bot Output:")
    print(f"  {result.bot_message[:120]}...")
    
    print(f"\n📊 Scores (out of 10):")
    dimensions = ["specificity", "category_fit", "merchant_fit", "trigger_relevance", "compulsion"]
    for dim in dimensions:
        bot_score = result.bot_scores.get(dim, 0)
        gold_score = result.gold_scores.get(dim, 0)
        gap = gold_score - bot_score
        
        status = "✅" if gap == 0 else "⚠️" if gap <= 2 else "❌"
        print(f"  {status} {dim:20s}: bot={bot_score:2d}  gold={gold_score:2d}  gap={gap:+2d}")
    
    if result.signals_found:
        print(f"\n✅ Signals Found: {', '.join(result.signals_found)}")
    
    if result.errors:
        print(f"\n❌ Issues:")
        for error in result.errors:
            print(f"   - {error}")


async def validate_all_cases(bot_url: str, max_cases: Optional[int] = None):
    """Validate bot against all case studies."""
    
    print(f"\n🔍 Vera Case Studies Validator")
    print(f"   Bot URL: {bot_url}")
    print(f"   Case Studies: {min(max_cases or len(CASE_STUDIES), len(CASE_STUDIES))}")
    print(f"{'='*80}\n")
    
    results = []
    total_gaps = {dim: 0 for dim in ["specificity", "category_fit", "merchant_fit", "trigger_relevance", "compulsion"]}
    
    cases_to_test = CASE_STUDIES[:max_cases] if max_cases else CASE_STUDIES
    
    for case in cases_to_test:
        case_id = case["case_id"]
        
        # Call bot
        bot_msg = await call_bot(
            bot_url,
            case_id,
            case["category"],
            case["merchant_name"],
            case["trigger"],
            case.get("customer")
        )
        
        # Score
        scores = {
            dim: score_dimension(bot_msg, case["gold_message"], dim)
            for dim in ["specificity", "category_fit", "merchant_fit", "trigger_relevance", "compulsion"]
        }
        
        # Signals
        signals_found, signals_missing = extract_signals(bot_msg, case.get("key_signals", []))
        
        # Gaps
        gaps = {
            dim: case["gold_scores"][dim] - scores[dim]
            for dim in scores.keys()
        }
        
        # Errors
        errors = []
        if len(bot_msg) > 320:
            errors.append(f"Message exceeds 320 chars: {len(bot_msg)}")
        if len(bot_msg.strip()) == 0:
            errors.append("Empty message")
        if any(url_pattern in bot_msg for url_pattern in ["http://", "https://"]):
            errors.append("Contains URL (should be stripped)")
        if signals_missing:
            errors.append(f"Missing key signals: {', '.join(signals_missing)}")
        
        # Tally gaps
        for dim, gap in gaps.items():
            total_gaps[dim] += gap
        
        result = ScoringResult(
            case_id=case_id,
            bot_message=bot_msg,
            gold_message=case["gold_message"],
            bot_scores=scores,
            gold_scores=case["gold_scores"],
            gaps=gaps,
            signals_found=signals_found,
            errors=errors
        )
        
        results.append(result)
        print_result(result)
    
    # Summary
    print(f"\n\n{'='*80}")
    print(f"📈 Summary Across {len(cases_to_test)} Cases")
    print(f"{'='*80}")
    
    print(f"\n📊 Average Gaps by Dimension (lower is better):")
    n = len(cases_to_test)
    for dim in ["specificity", "category_fit", "merchant_fit", "trigger_relevance", "compulsion"]:
        avg_gap = total_gaps[dim] / n if n > 0 else 0
        status = "✅" if avg_gap < 1 else "⚠️" if avg_gap < 3 else "❌"
        print(f"  {status} {dim:20s}: {avg_gap:.2f} points behind gold")
    
    total_score = sum(r.bot_scores.values() for r in results)
    max_score = sum(r.gold_scores.values() for r in results)
    pct = 100 * total_score / max_score if max_score > 0 else 0
    
    print(f"\n🏆 Overall: {total_score}/{max_score} ({pct:.1f}%)")
    
    error_cases = [r for r in results if r.errors]
    if error_cases:
        print(f"\n⚠️  {len(error_cases)} cases with issues:")
        for r in error_cases:
            print(f"   Case #{r.case_id}: {r.errors[0]}")


def main():
    parser = argparse.ArgumentParser(description="Validate Vera bot against case studies")
    parser.add_argument(
        "--bot-url",
        default="https://kkalra-vera-magicpin.hf.space",
        help="Bot endpoint URL"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local bot (http://localhost:8080)"
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=None,
        help="Limit to N cases"
    )
    
    args = parser.parse_args()
    
    if args.local:
        args.bot_url = "http://localhost:8080"
    
    import asyncio
    asyncio.run(validate_all_cases(args.bot_url, args.cases))


if __name__ == "__main__":
    main()
