"""
EarthWhispers — End-to-End Demo Replay Script

Simulates a full pipeline run:
  signal event → fetch observations → XGBoost prediction →
  impact lookup → Gemini summary → policy check → output

Usage:
    python replay.py                        # uses default high-risk event
    python replay.py --event evt_001        # replay a specific event
    python replay.py --event evt_003 --verbose
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "agent"))

from tools.fetch_observations import fetch_observations
from tools.predict_tool import predict_flood_risk
from tools.impact_tool import query_impact_graph
from tools.summarize_tool import summarize_with_gemini
from policy.alert_policy import check_alert_policy

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
ORANGE = "\033[33m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
GRAY   = "\033[90m"

RISK_COLOR = {"high": RED, "medium": ORANGE, "low": GREEN}

EVENTS = {
    "evt_001": ("catchment_brahmaputra_assam", "MEDIUM risk scenario — Oct 10"),
    "evt_002": ("catchment_brahmaputra_assam", "LOW risk scenario — Oct 11"),
    "evt_003": ("catchment_brahmaputra_assam", "HIGH risk scenario — Oct 12 (recommended)"),
}


def banner(text: str):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


def step(num: int, text: str):
    print(f"\n{BOLD}[Step {num}]{RESET} {text}")


def ok(text: str):
    print(f"  {GREEN}✓{RESET} {text}")


def info(key: str, value):
    print(f"  {GRAY}{key}:{RESET} {value}")


def main():
    parser = argparse.ArgumentParser(description="EarthWhispers demo replay")
    parser.add_argument("--event", default="evt_003", choices=list(EVENTS.keys()),
                        help="Event ID to replay (default: evt_003 — HIGH risk)")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON at each step")
    args = parser.parse_args()

    area_id, scenario = EVENTS[args.event]

    banner(f"EarthWhispers — Demo Replay")
    print(f"  Scenario : {scenario}")
    print(f"  Event ID : {args.event}")
    print(f"  Area     : {area_id}")

    total_start = time.time()

    # ── Step 1: Fetch observations ────────────────────────────────────────────
    step(1, "Fetching latest signal observations...")
    t = time.time()
    observations = fetch_observations(area_id, event_id=args.event)

    if "error" in observations:
        print(f"  {RED}✗ {observations['error']}{RESET}")
        sys.exit(1)

    ok(f"Signal event: {observations['event_id']}")
    info("Area", observations.get("area_name"))
    info("Observation time", observations.get("event_time"))
    info("Data quality", observations.get("data_quality"))
    info("24h rainfall", f"{observations.get('rainfall_24h')} mm")
    info("Anomaly score", f"{observations.get('anomaly_score')}x above baseline")
    info("Signal rule", observations.get("triggered_rule"))
    info("Source", observations.get("source"))
    print(f"  {GRAY}({time.time()-t:.2f}s){RESET}")

    if args.verbose:
        print(f"\n  {GRAY}{json.dumps(observations, indent=4)}{RESET}")

    # ── Step 2: XGBoost prediction ────────────────────────────────────────────
    step(2, "Calling XGBoost prediction model...")
    t = time.time()
    prediction = predict_flood_risk(observations["event_id"], observations)

    risk_class = prediction.get("risk_class", "low")
    risk_score = prediction.get("risk_score", 0)
    color = RISK_COLOR.get(risk_class, RESET)

    ok(f"Risk class: {color}{BOLD}{risk_class.upper()}{RESET}  |  Score: {color}{risk_score:.2f}{RESET}")
    info("Model version", prediction.get("model_version"))
    info("Experimental", prediction.get("is_experimental"))
    print(f"  {GRAY}({time.time()-t:.2f}s){RESET}")

    if args.verbose:
        print(f"\n  {GRAY}{json.dumps(prediction, indent=4)}{RESET}")

    # ── Step 3: Impact lookup ─────────────────────────────────────────────────
    step(3, "Querying impact context (communities & assets)...")
    t = time.time()
    impact = query_impact_graph(area_id)

    settlements = impact.get("nearby_settlements", [])
    assets = impact.get("critical_assets", [])

    ok(f"Found {len(settlements)} nearby communities, {len(assets)} critical assets")
    for s in settlements:
        info(f"  Community", f"{s['name']} — pop. {s['population']:,} ({s['distance_km']} km)")
    for a in assets:
        info(f"  Asset", f"{a['name']} ({a['type']}) — {a['distance_km']} km")
    print(f"  {GRAY}({time.time()-t:.2f}s){RESET}")

    # ── Step 4: Gemini explanation ────────────────────────────────────────────
    step(4, "Generating Gemini evidence-grounded explanation...")
    t = time.time()
    summary_result = summarize_with_gemini(
        area_name=observations.get("area_name", area_id),
        risk_score=risk_score,
        risk_class=risk_class,
        observations=observations,
        impact=impact,
        model_version=prediction.get("model_version", "unknown"),
        is_experimental=prediction.get("is_experimental", True),
    )

    ok("Summary generated")
    print(f"\n  {BOLD}Summary:{RESET}")
    for line in summary_result["summary"].splitlines():
        print(f"    {line}")

    print(f"\n  {BOLD}Recommended Actions:{RESET}")
    for i, action in enumerate(summary_result["recommended_actions"], 1):
        print(f"    {i}. {action}")
    print(f"  {GRAY}({time.time()-t:.2f}s){RESET}")

    # ── Step 5: Policy check ──────────────────────────────────────────────────
    step(5, "Running alert policy check...")
    t = time.time()
    policy_result = check_alert_policy(
        area_id=area_id,
        risk_class=risk_class,
        risk_score=risk_score,
        data_quality=observations.get("data_quality", "unknown"),
    )

    decision = policy_result["decision"]
    decision_color = {"send_alert": GREEN, "suppress": GRAY, "human_review": ORANGE}.get(decision, RESET)

    ok(f"Decision: {decision_color}{BOLD}{decision.upper()}{RESET}")
    info("Reason", policy_result["reason"])
    print(f"  {GRAY}({time.time()-t:.2f}s){RESET}")

    # ── Final summary ─────────────────────────────────────────────────────────
    banner("Replay Complete")
    print(f"  Total time : {time.time()-total_start:.2f}s")
    print(f"  Event      : {args.event} — {observations.get('area_name')}")
    print(f"  Risk       : {color}{BOLD}{risk_class.upper()} ({risk_score:.2f}){RESET}")
    print(f"  Decision   : {decision_color}{BOLD}{decision.upper()}{RESET}")
    print(f"\n  {GRAY}View on dashboard: http://localhost:8501{RESET}\n")


if __name__ == "__main__":
    main()
