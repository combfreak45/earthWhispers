"""
Unit tests for policy engine deduplication and safety gates.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent")))

from policy_engine import evaluate_alert_policy, DISCLAIMER_TEXT


def test_nominal_risk_not_dispatched():
    pol = evaluate_alert_policy(
        catchment_id="test_basin",
        risk_class=0,
        risk_score=0.08,
        data_freshness_status="FRESH_NOMINAL",
        mode="live"
    )
    assert pol["should_dispatch_alert"] is False
    assert pol["policy_action"] == "LOGGED_NOMINAL"
    assert "experimental research prototype" in pol["disclaimer"]


def test_stale_critical_suppression():
    pol = evaluate_alert_policy(
        catchment_id="test_basin",
        risk_class=2,
        risk_score=0.85,
        data_freshness_status="STALE_CRITICAL",
        mode="live"
    )
    assert pol["should_dispatch_alert"] is False
    assert pol["policy_action"] == "SUPPRESSED_STALE_DATA"


def test_cooldown_deduplication():
    # First high risk dispatch
    pol1 = evaluate_alert_policy(
        catchment_id="cooldown_basin",
        risk_class=1,
        risk_score=0.65,
        data_freshness_status="FRESH_NOMINAL",
        mode="live",
        cooldown_hours=6.0
    )
    assert pol1["should_dispatch_alert"] is True

    # Immediate second event with same severity should be suppressed
    pol2 = evaluate_alert_policy(
        catchment_id="cooldown_basin",
        risk_class=1,
        risk_score=0.68,
        data_freshness_status="FRESH_NOMINAL",
        mode="live",
        cooldown_hours=6.0
    )
    assert pol2["should_dispatch_alert"] is False
    assert pol2["policy_action"] == "SUPPRESSED_COOLDOWN"

    # Escalated severity should bypass cooldown
    pol3 = evaluate_alert_policy(
        catchment_id="cooldown_basin",
        risk_class=2,
        risk_score=0.92,
        data_freshness_status="FRESH_NOMINAL",
        mode="live",
        cooldown_hours=6.0
    )
    assert pol3["should_dispatch_alert"] is True
