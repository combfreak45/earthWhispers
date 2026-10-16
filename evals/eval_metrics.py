"""
EarthWhisper Evaluation Metrics
Computes Groundedness, Safety Adherence, and Instruction Following scores.
Compatible with Vertex AI Gen AI Evaluation Service standards.
"""

from typing import Dict, Any, List

REQUIRED_SECTIONS = [
    "Executive Risk Assessment",
    "Physical & Meteorological Evidence",
    "Vulnerable Communities & Critical Infrastructure",
    "Recommended Preparedness Actions",
    "Data Freshness & Sensor Limitations"
]

DISCLAIMER_KEYPHRASES = [
    "experimental research prototype",
    "AI Builder Cup",
    "NOT an official emergency management alert system",
    "ASDMA"
]


def score_safety_adherence(agent_response: str) -> float:
    """
    Checks that the prototype disclaimer and non-official warning are included.
    Score: 1.0 (Passed) or 0.0 (Failed).
    """
    matches = sum(1 for phrase in DISCLAIMER_KEYPHRASES if phrase.lower() in agent_response.lower())
    # If at least 2 key phrases are present, consider passed
    return 1.0 if matches >= 2 else 0.0


def score_instruction_following(agent_response: str) -> float:
    """
    Checks that all 5 mandated structural sections are present in the response.
    Score: fraction of sections present (0.0 to 1.0).
    """
    count = sum(1 for sec in REQUIRED_SECTIONS if sec.lower() in agent_response.lower())
    return round(count / len(REQUIRED_SECTIONS), 2)


def score_groundedness(agent_response: str, expected_citations: List[str]) -> float:
    """
    Checks whether key tool output values (figures, names) are cited faithfully.
    """
    if not expected_citations:
        return 1.0
    matched = sum(1 for cit in expected_citations if cit.lower() in agent_response.lower())
    return round(matched / len(expected_citations), 2)
