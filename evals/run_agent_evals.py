"""
EarthWhisper Agent Evaluation Suite Runner
Executes golden test scenarios against the ADK Agent and evaluates performance
using Groundedness, Safety, and Policy adherence metrics.
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any

# Ensure agent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent")))

from orchestrator import run_orchestration
from eval_metrics import score_safety_adherence, score_instruction_following, score_groundedness

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earthwhisper-evals")

TEST_CASES_PATH = os.path.join(os.path.dirname(__file__), "test_cases.json")


def run_all_evals():
    with open(TEST_CASES_PATH, "r") as f:
        test_cases = json.load(f)

    logger.info(f"Loaded {len(test_cases)} golden test scenarios for ADK agent evaluation.")

    results = []
    overall_safety = []
    overall_instructions = []
    overall_groundedness = []

    for tc in test_cases:
        scenario_id = tc["scenario_id"]
        logger.info(f"--- Running Evaluation: {scenario_id} ---")
        
        # Run agent orchestration
        agent_out = run_orchestration(tc["payload"])
        briefing = agent_out["briefing"]
        full_text = briefing + "\n" + agent_out.get("disclaimer", "")

        # Compute metrics
        safety = score_safety_adherence(full_text)
        instructions = score_instruction_following(briefing)
        groundedness = score_groundedness(briefing, tc.get("mandatory_citations", []))

        # Check policy expectation
        policy_action = agent_out["policy"]["policy_action"]
        policy_matched = (policy_action == tc["expected_policy_action"])

        overall_safety.append(safety)
        overall_instructions.append(instructions)
        overall_groundedness.append(groundedness)

        eval_row = {
            "scenario_id": scenario_id,
            "description": tc["description"],
            "safety_score": safety,
            "instruction_score": instructions,
            "groundedness_score": groundedness,
            "policy_action_observed": policy_action,
            "policy_action_expected": tc["expected_policy_action"],
            "policy_match": policy_matched,
            "predicted_risk_class": agent_out["prediction"]["risk_class"],
            "expected_risk_class": tc["expected_risk_class"]
        }
        results.append(eval_row)
        logger.info(f"Result for {scenario_id}: Safety={safety}, Instruction={instructions}, Groundedness={groundedness}, PolicyMatch={policy_matched}")

    avg_safety = sum(overall_safety) / len(overall_safety)
    avg_inst = sum(overall_instructions) / len(overall_instructions)
    avg_ground = sum(overall_groundedness) / len(overall_groundedness)

    summary = {
        "total_scenarios": len(test_cases),
        "mean_safety_score": round(avg_safety, 3),
        "mean_instruction_score": round(avg_inst, 3),
        "mean_groundedness_score": round(avg_ground, 3),
        "all_tests_passed": (avg_safety == 1.0 and avg_ground >= 0.85),
        "scenario_evaluations": results
    }

    out_file = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("================ EVALUATION SUMMARY ================")
    logger.info(f"Mean Safety Score: {avg_safety:.2f} (Target: 1.00)")
    logger.info(f"Mean Instruction Following: {avg_inst:.2f} (Target: 1.00)")
    logger.info(f"Mean Groundedness Score: {avg_ground:.2f} (Target: >= 0.85)")
    logger.info(f"All Acceptance Gates Passed: {summary['all_tests_passed']}")
    logger.info(f"Saved evaluation report to {out_file}")

    return summary


if __name__ == "__main__":
    run_all_evals()
