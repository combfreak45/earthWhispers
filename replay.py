"""
EarthWhispers — End-to-End Demo Replay Script

Runs the full LIVE pipeline via the deterministic orchestrator:
  catchment_features -> Vertex prediction -> climate baseline ->
  impact lookup -> Gemini summary -> policy check -> alert_audits write

Usage:
    python replay.py                               # live, default catchment
    python replay.py --catchment brahmaputra_lower_assam
    python replay.py --mode mock --scenario 2024_ASSAM_BRAHMAPUTRA_SURGE --verbose
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "agent"))

from pipeline import run_assessment

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
ORANGE = "\033[33m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
GRAY   = "\033[90m"

RISK_COLOR = {"High": RED, "Moderate": ORANGE, "Low": GREEN}
DECISION_COLOR = {"send_alert": GREEN, "suppress": GRAY, "human_review": ORANGE}


def banner(text: str):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


def section(text: str):
    print(f"\n{BOLD}> {text}{RESET}")


def info(key: str, value):
    print(f"  {GRAY}{key}:{RESET} {value}")


def main():
    parser = argparse.ArgumentParser(description="EarthWhispers demo replay")
    parser.add_argument("--catchment", default="brahmaputra_lower_assam", help="Catchment ID to assess")
    parser.add_argument("--mode", default="live", choices=["live", "mock"], help="Execution mode")
    parser.add_argument(
        "--scenario",
        default="2024_ASSAM_BRAHMAPUTRA_SURGE",
        choices=[
            "2024_ASSAM_BRAHMAPUTRA_SURGE",
            "2022_ASSAM_CATASTROPHIC",
            "2017_ASSAM_BENCHMARK",
            "DRY_SEASON_NOMINAL",
            "STALE_DATA_DEGRADED",
        ],
        help="Replay scenario (for --mode mock)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print full JSON result")
    args = parser.parse_args()

    banner(f"EarthWhispers — {args.mode.upper()} Pipeline Replay")
    print(f"  Catchment : {args.catchment}")
    print(f"  Mode      : {args.mode}")
    if args.mode == "mock":
        print(f"  Scenario  : {args.scenario}")

    t = time.time()
    result = run_assessment(catchment_id=args.catchment, mode=args.mode, scenario_id=args.scenario)

    if result.get("status") != "ok":
        print(f"\n  {RED}x Assessment did not complete: {result.get('error', result.get('status'))}{RESET}")
        sys.exit(1)

    pred = result["prediction"]
    risk_label = pred["risk_label"]
    risk_score = pred["risk_score"]
    color = RISK_COLOR.get(risk_label, RESET)

    # ── Telemetry ──
    section("Telemetry (catchment_features)")
    info("Observed at", result["observation_timestamp"])
    info("Freshness", result["freshness_status"])
    f = result["features"]
    info("24h rainfall", f"{f.get('rain_24h_mm')} mm")
    info("72h rainfall", f"{f.get('rain_72h_mm')} mm")
    info("24h anomaly", f"{f.get('rain_24h_anomaly_pct')}% vs normal")
    info("72h z-score", f.get("rain_72h_zscore"))

    # ── Prediction ──
    section("Vertex AI prediction")
    print(f"  Risk: {color}{BOLD}{risk_label.upper()}{RESET}  |  Score: {color}{risk_score:.2f}{RESET}  |  Class: {pred['risk_class']}")
    info("Probabilities", pred.get("class_probabilities"))
    info("Model version", pred.get("model_version"))

    # ── Baseline ──
    base = result.get("baseline", {})
    section("Seasonal baseline")
    if "error" in base:
        info("Baseline", base["error"])
    else:
        info("Mean 24h", f"{base.get('mean_rain_24h_mm')} mm (± {base.get('std_rain_24h_mm')})")
        info("Mean 72h", f"{base.get('mean_rain_72h_mm')} mm (± {base.get('std_rain_72h_mm')})")

    # ── Impact ──
    impact = result["impact"]
    section("Impact (exposed assets & population)")
    info("Exposed population", f"{impact.get('total_exposed_population', 0):,}")
    info("Affected assets", result["affected_assets_count"])
    for name in impact.get("exposed_settlements", [])[:5]:
        info("  Settlement", name)
    for name in impact.get("critical_hospitals", []):
        info("  Hospital", name)

    # ── Summary ──
    section("Gemini briefing")
    for line in result["summary"].splitlines():
        print(f"    {line}")
    if result.get("recommended_actions"):
        print(f"\n  {BOLD}Recommended Actions:{RESET}")
        for i, action in enumerate(result["recommended_actions"], 1):
            print(f"    {i}. {action}")

    # ── Policy ──
    policy = result["policy"]
    decision = policy["decision"]
    dcolor = DECISION_COLOR.get(decision, RESET)
    section("Alert policy")
    print(f"  Decision: {dcolor}{BOLD}{decision.upper()}{RESET}")
    info("Reason", policy["reason"])

    # ── Audit ──
    section("Audit (alert_audits)")
    info("Trace ID", result.get("trace_id"))
    info("Audit", result.get("audit"))

    banner("Replay Complete")
    print(f"  Total time : {time.time()-t:.2f}s")
    print(f"  Risk       : {color}{BOLD}{risk_label.upper()} ({risk_score:.2f}){RESET}")
    print(f"  Decision   : {dcolor}{BOLD}{decision.upper()}{RESET}\n")

    if args.verbose:
        print(f"{GRAY}{json.dumps(result, indent=2, default=str)}{RESET}")


if __name__ == "__main__":
    main()