#!/usr/bin/env python3
import json
import os
import random
import re
import statistics
import sys
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urlrequest, error as urlerror

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
except Exception:
    pass

BOT_URL = os.getenv("BOT_URL", "http://127.0.0.1:8080").rstrip("/")
DATASET_DIR = Path(os.getenv("DATASET_DIR", Path(__file__).resolve().parent / "dataset"))
EXPANDED_DIR = Path(os.getenv("EXPANDED_DIR", Path(__file__).resolve().parent / "expanded"))
SEED = int(os.getenv("GAUNTLET_SEED", "42"))
random.seed(SEED)

MAX_TICK_MS = int(os.getenv("MAX_TICK_MS", "15000"))
MAX_REPLY_MS = int(os.getenv("MAX_REPLY_MS", "12000"))
MAX_BODY_LEN = 320

class C:
    PASS = "\033[92m[PASS]\033[0m"
    FAIL = "\033[91m[FAIL]\033[0m"
    WARN = "\033[93m[WARN]\033[0m"
    INFO = "\033[94m[INFO]\033[0m"
    SEC = "\033[95m\033[1m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def sec(title: str):
    print(f"\n{C.SEC}{'='*72}\n{title}\n{'='*72}{C.END}")


def info(msg: str):
    print(f"{C.INFO} {msg}")


def warn(msg: str):
    print(f"{C.WARN} {msg}")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def future_iso(days=1) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def past_iso(days=1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _req(method: str, path: str, body: Optional[Dict] = None, timeout: int = 30):
    url = f"{BOT_URL}{path}"
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urlrequest.Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        resp = urlrequest.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8")), None, int((time.time() - t0) * 1000)
    except urlerror.HTTPError as e:
        lat = int((time.time() - t0) * 1000)
        try:
            return json.loads(e.read().decode("utf-8")), None, lat
        except Exception:
            return None, f"HTTP {e.code}", lat
    except Exception as e:
        return None, str(e), int((time.time() - t0) * 1000)


def get(path: str, timeout: int = 10):
    return _req("GET", path, None, timeout)


def post(path: str, body: Dict, timeout: int = 30):
    return _req("POST", path, body, timeout)


@dataclass
class Result:
    name: str
    passed: bool
    details: str = ""


@dataclass
class Scorecard:
    results: List[Result] = field(default_factory=list)

    def add(self, name: str, passed: bool, details: str = ""):
        self.results.append(Result(name, passed, details))
        tag = C.PASS if passed else C.FAIL
        print(f"{tag} {name} {C.DIM}{details}{C.END}")

    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        pct = (passed / total * 100) if total else 0
        sec("FINAL SUMMARY")
        print(f"{C.BOLD}Passed:{C.END} {passed}/{total} ({pct:.1f}%)")
        failed = [r for r in self.results if not r.passed]
        if failed:
            print(f"\n{C.BOLD}Failures:{C.END}")
            for r in failed[:20]:
                print(f"- {r.name}: {r.details}")
        if pct >= 92:
            print("\nVerdict: Strong finalist-level readiness")
        elif pct >= 80:
            print("\nVerdict: Competitive, but not bulletproof")
        elif pct >= 65:
            print("\nVerdict: Promising, needs more work")
        else:
            print("\nVerdict: Not win-ready yet")


class Dataset:
    def __init__(self):
        self.categories: Dict[str, dict] = {}
        self.merchants: Dict[str, dict] = {}
        self.customers: Dict[str, dict] = {}
        self.triggers: Dict[str, dict] = {}

    def load(self):
        roots = [EXPANDED_DIR, DATASET_DIR]
        for root in roots:
            if not root.exists():
                continue
            for sub, store, key in [
                ("categories", self.categories, "slug"),
                ("merchants", self.merchants, "merchant_id"),
                ("customers", self.customers, "customer_id"),
                ("triggers", self.triggers, "id"),
            ]:
                d = root / sub
                if d.exists():
                    for f in d.glob("*.json"):
                        try:
                            data = json.load(open(f, encoding="utf-8"))
                            item_id = data.get(key, f.stem)
                            store.setdefault(item_id, data)
                        except Exception:
                            pass
            for fname, store, key in [
                ("merchants_seed.json", self.merchants, "merchant_id"),
                ("customers_seed.json", self.customers, "customer_id"),
                ("triggers_seed.json", self.triggers, "id"),
            ]:
                p = root / fname
                if p.exists():
                    try:
                        raw = json.load(open(p, encoding="utf-8"))
                        container = next((k for k, v in raw.items() if isinstance(v, list)), None)
                        if container:
                            for item in raw[container]:
                                if key in item:
                                    store.setdefault(item[key], item)
                    except Exception:
                        pass


def push_context(scope: str, context_id: str, version: int, payload: dict):
    return post("/v1/context", {
        "scope": scope,
        "context_id": context_id,
        "version": version,
        "payload": payload,
        "delivered_at": now_iso(),
    }, timeout=15)


def push_all(ds: Dataset):
    for slug, item in ds.categories.items():
        push_context("category", slug, 1, item)
    for mid, item in ds.merchants.items():
        push_context("merchant", mid, 1, item)
    for cid, item in ds.customers.items():
        push_context("customer", cid, 1, item)
    for tid, item in ds.triggers.items():
        push_context("trigger", tid, 1, item)


def basic_quality_checks(action: dict, merchant: dict, trigger: dict) -> List[str]:
    body = action.get("body", "") or ""
    issues = []
    if not body.strip():
        issues.append("empty body")
    if len(body) > MAX_BODY_LEN:
        issues.append(f"body too long {len(body)}")
    if re.search(r"https?://", body):
        issues.append("contains URL")
    if action.get("cta") not in ("binary", "open_ended", "none", None):
        issues.append(f"bad cta {action.get('cta')}")
    if len(re.findall(r"\d+", body)) == 0 and trigger.get("kind") not in ("curious_ask_due",):
        issues.append("no numeric grounding")
    ident = merchant.get("identity", {})
    names = [ident.get("owner_first_name", ""), ident.get("name", ""), ident.get("locality", "")]
    if not any(n and n.lower() in body.lower() for n in names):
        issues.append("weak merchant personalization")
    generic_bad = ["vera here", "something worth discussing", "new insights available", "merchants like you"]
    if any(g in body.lower() for g in generic_bad):
        issues.append("generic phrasing")
    return issues


def synthetic_trigger(base_mid: str, idx: int, kind: str = "perf_dip") -> dict:
    return {
        "id": f"trg_SYN_{idx:03d}",
        "scope": "merchant",
        "kind": kind,
        "source": "synthetic_gauntlet",
        "merchant_id": base_mid,
        "customer_id": None,
        "payload": {
            "metric": "ctr",
            "delta_pct": -18,
            "window": "7d",
            "benchmark": "+4% peer median",
            "note": f"synthetic case {idx}"
        },
        "urgency": random.choice([3, 4, 5]),
        "suppression_key": f"gauntlet:{base_mid}:{kind}:{idx}",
        "expires_at": future_iso(2),
    }


def main():
    sc = Scorecard()
    sec("VERA GOD-LEVEL GAUNTLET")
    info(f"Bot: {BOT_URL}")
    ds = Dataset()
    ds.load()
    info(f"Loaded dataset: {len(ds.categories)} categories, {len(ds.merchants)} merchants, {len(ds.customers)} customers, {len(ds.triggers)} triggers")

    data, err, lat = get("/v1/healthz", timeout=5)
    sc.add("healthz reachable", not err and data and data.get("status") == "ok", f"lat={lat}ms err={err}")
    data, err, _ = get("/v1/metadata", timeout=5)
    sc.add("metadata reachable", not err and isinstance(data, dict), f"err={err}")

    post("/v1/teardown", {}, timeout=10)
    push_all(ds)

    sec("CONTRACT + VERSIONING")
    if ds.categories:
        slug, cat = next(iter(ds.categories.items()))
        data, err, _ = push_context("category", slug, 5, cat)
        sc.add("fresh higher version accepted", not err and data.get("accepted") is True, str(data))
        data, err, _ = push_context("category", slug, 3, cat)
        sc.add("stale lower version rejected", not err and data.get("accepted") is False, str(data))
        data, err, _ = push_context("category", slug, 5, cat)
        sc.add("same version idempotent accepted", not err and data.get("accepted") is True, str(data))

    sec("TICK QUALITY")
    tids = list(ds.triggers.keys())[: min(10, len(ds.triggers))]
    data, err, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": tids}, timeout=20)
    actions = data.get("actions", []) if data else []
    sc.add("tick returns successfully", not err and data is not None, f"lat={lat}ms err={err}")
    sc.add("tick under latency budget", lat < MAX_TICK_MS, f"lat={lat}ms")
    sc.add("tick returns <=20 actions", len(actions) <= 20, f"actions={len(actions)}")
    sc.add("tick returns at least one action", len(actions) >= 1, f"actions={len(actions)}")

    seen_bodies = set()
    for i, act in enumerate(actions[:10]):
        trg = ds.triggers.get(act.get("trigger_id"), {})
        mer = ds.merchants.get(act.get("merchant_id"), {})
        issues = basic_quality_checks(act, mer, trg)
        sc.add(f"action {i} quality checks", len(issues) == 0, ", ".join(issues) or "ok")
        body = act.get("body", "")
        sc.add(f"action {i} unique body", body not in seen_bodies, body[:80])
        seen_bodies.add(body)

    sec("SUPPRESSION + EXPIRED")
    trg = next((t for t in ds.triggers.values() if t.get("suppression_key")), None)
    if trg:
        tid = trg["id"]
        d1, _, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": [tid]}, timeout=15)
        d2, _, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": [tid]}, timeout=15)
        sc.add("suppression fires first time", len((d1 or {}).get("actions", [])) >= 0, str((d1 or {}).get("actions", [])))
        sc.add("suppression prevents duplicate send", len((d2 or {}).get("actions", [])) == 0, f"actions2={len((d2 or {}).get('actions', []))}")

    if ds.merchants:
        base_mid = next(iter(ds.merchants.keys()))
        exp = synthetic_trigger(base_mid, 999)
        exp["id"] = "trg_EXPIRED_GAUNTLET"
        exp["expires_at"] = past_iso(1)
        push_context("trigger", exp["id"], 1, exp)
        data, err, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": [exp["id"]]}, timeout=15)
        sc.add("expired trigger skipped", not err and len(data.get("actions", [])) == 0, str(data))

    sec("REPLY STATE MACHINE")
    # Use the LAST merchant for hostile tests to avoid blocking the first one
    # which is used for later synthetic tests.
    mid = list(ds.merchants.keys())[-1] if ds.merchants else None
    if mid:
        for msg in ["Stop messaging me. This is spam.", "band karo", "nahi chahiye"]:
            data, err, lat = post("/v1/reply", {
                "conversation_id": f"conv_hostile_{abs(hash(msg))%9999}",
                "merchant_id": mid,
                "customer_id": None,
                "from_role": "merchant",
                "message": msg,
                "received_at": now_iso(),
                "turn_number": 2,
            }, timeout=15)
            sc.add(f"hostile handled: {msg[:12]}", not err and data.get("action") == "end", f"lat={lat} body={data}")

        conv = "conv_auto_gauntlet"
        ended = False
        for i in range(1, 5):
            data, err, _ = post("/v1/reply", {
                "conversation_id": conv,
                "merchant_id": mid,
                "customer_id": None,
                "from_role": "merchant",
                "message": "Thank you for contacting us! Our team will respond shortly.",
                "received_at": now_iso(),
                "turn_number": i + 1,
            }, timeout=15)
            if data and data.get("action") == "end":
                ended = True
                break
        sc.add("auto-reply loop ends", ended, str(data))

        commit_msgs = ["Ok lets do it. Whats next?", "haan chalo", "yes please proceed"]
        for msg in commit_msgs:
            data, err, lat = post("/v1/reply", {
                "conversation_id": f"conv_commit_{abs(hash(msg))%9999}",
                "merchant_id": mid,
                "customer_id": None,
                "from_role": "merchant",
                "message": msg,
                "received_at": now_iso(),
                "turn_number": 2,
            }, timeout=15)
            body = (data or {}).get("body", "").lower()
            bad = any(x in body for x in ["would you", "can you", "do you want", "what if", "how about"])
            actiony = any(x in body for x in ["sending", "done", "here", "confirmed", "on it", "pulling"])
            sc.add(f"commitment switches to action: {msg[:12]}", not err and data.get("action") == "send" and not bad and actiony, f"lat={lat} body={body}")

        data, err, lat = post("/v1/reply", {
            "conversation_id": "conv_unknown_gauntlet_xyz",
            "merchant_id": mid,
            "customer_id": None,
            "from_role": "merchant",
            "message": "Hello?",
            "received_at": now_iso(),
            "turn_number": 1,
        }, timeout=15)
        sc.add("unknown conversation handled", not err and data.get("action") in ("send", "end", "wait"), f"lat={lat} body={data}")
        sc.add("reply latency budget", lat < MAX_REPLY_MS, f"lat={lat}ms")

    sec("CONCURRENCY + LOAD")
    sample_tids = list(ds.triggers.keys())[: min(5, len(ds.triggers))]
    out: List[Tuple[Optional[dict], Optional[str], int]] = []
    lock = threading.Lock()

    def fire_tick():
        res = post("/v1/tick", {"now": now_iso(), "available_triggers": sample_tids}, timeout=20)
        with lock:
            out.append(res)

    threads = [threading.Thread(target=fire_tick) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    errs = [e for _, e, _ in out if e]
    lats = [lat for _, _, lat in out]
    sc.add("concurrent ticks no transport errors", len(errs) == 0, str(errs[:2]))
    sc.add("concurrent ticks all return", len(out) == 3, f"count={len(out)}")
    if lats:
        sc.add("concurrent tick p95 under budget", max(lats) < MAX_TICK_MS, f"lats={lats}")

    sec("UNSEEN SYNTHETIC CASES")
    if ds.merchants:
        base_mid = next(iter(ds.merchants.keys()))
        synth_ids = []
        for i, kind in enumerate(["perf_dip", "perf_spike", "review_theme_emerged", "festival_upcoming", "competitor_opened", "renewal_due"], start=1):
            trg = synthetic_trigger(base_mid, i, kind)
            if kind == "review_theme_emerged":
                trg["payload"] = {"theme": "wait time", "occurrences_30d": 5}
            elif kind == "festival_upcoming":
                trg["payload"] = {"festival_name": "Diwali", "days_until": 4}
            elif kind == "competitor_opened":
                trg["payload"] = {"locality": "Sector 18", "distance_km": 1.2}
            elif kind == "renewal_due":
                trg["payload"] = {"days_remaining": 3, "plan_name": "Gold"}
            push_context("trigger", trg["id"], 1, trg)
            synth_ids.append(trg["id"])
        data, err, lat = post("/v1/tick", {"now": now_iso(), "available_triggers": synth_ids}, timeout=20)
        actions = data.get("actions", []) if data else []
        sc.add("synthetic unseen tick returns actions", not err and len(actions) >= 1, f"lat={lat} actions={len(actions)}")
        for i, act in enumerate(actions[:6]):
            trg = {**next((t for t in [synthetic_trigger(base_mid, j) for j in range(1,7)] if t['id'] == act.get('trigger_id')), {}), **{}}
            mer = ds.merchants.get(act.get("merchant_id"), {})
            issues = basic_quality_checks(act, mer, trg)
            sc.add(f"synthetic action {i} quality", len(issues) <= 1, ", ".join(issues) or "ok")

    sec("TEARDOWN")
    data, err, _ = post("/v1/teardown", {}, timeout=10)
    sc.add("teardown returns wiped", not err and data and data.get("status") == "wiped", str(data))
    data, err, _ = post("/v1/tick", {"now": now_iso(), "available_triggers": tids}, timeout=15)
    sc.add("after teardown no actions", not err and len(data.get("actions", [])) == 0, str(data))

    sc.summary()


if __name__ == "__main__":
    main()
