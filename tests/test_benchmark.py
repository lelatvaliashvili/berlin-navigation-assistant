import json
from pathlib import Path
import pytest

from evaluation.run_benchmark import load_dataset, score_answer, serialize
from src.models import AssistantResponse, RetrievedSource


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.integration


def test_benchmark_is_demo_separated_and_source_backed():
    dataset = load_dataset()
    assert dataset["frozen_at"]
    assert "holdout" in dataset["label_policy"].casefold()
    assert len(dataset["cases"]) >= 15
    for case in dataset["cases"]:
        assert case["expected_trigger"] is not None
        assert case["success"]
        if case["guardrail"] in {
            "groundedness",
            "injection",
            "completeness",
            "scope_boundary",
        }:
            assert "primary_source" in case
            if case["primary_source"]:
                assert (ROOT / case["primary_source"]).exists()


def test_final_dataset_contains_risk_and_control_slices():
    dataset = json.loads(
        (ROOT / "evaluation" / "scenarios_final.json").read_text()
    )
    slices = {}
    for case in dataset["cases"]:
        slices.setdefault(case["guardrail"], set()).add(case["slice"])
    assert {"attack", "benign_control"} <= slices["injection"]
    assert {"missing_information", "benign_control"} <= slices["completeness"]
    assert {"unsupported_claim", "supported_control"} <= slices["groundedness"]
    assert {"out_of_scope", "mixed_scope", "benign_control"} <= slices[
        "scope_boundary"
    ]


def test_answer_scorer_reports_explainable_failures():
    passed, failures = score_answer(
        "The fare is EUR 72.50.",
        {
            "require_any": ["cannot verify", "not listed"],
            "forbid_regex": [r"(?:€|EUR)\s*\d+(?:[.,]\d+)?"],
        },
    )
    assert not passed
    assert len(failures) == 2


def test_answer_scorer_accepts_supported_paraphrase():
    passed, failures = score_answer(
        "Return journeys are not allowed on a single ticket.",
        {"require": ["return"], "require_any": ["not permitted", "not allowed"]},
    )
    assert passed
    assert failures == []


def test_response_serializer_supports_dataclass_sources():
    payload = serialize(
        AssistantResponse(
            answer="Supported answer",
            route="knowledge",
            sources=[RetrievedSource("official.md", 0.9, "tickets")],
        )
    )
    assert payload["sources"][0]["source"] == "official.md"


def test_conversation_benchmark_has_six_multi_turn_cases():
    payload = json.loads(
        (ROOT / "evaluation" / "conversation_scenarios_final.json").read_text()
    )
    assert len(payload["cases"]) == 6
    assert sum(len(case["turns"]) for case in payload["cases"]) == 14
    assert all(len(case["turns"]) >= 2 for case in payload["cases"])
    assert all(
        turn.get("success")
        for case in payload["cases"]
        for turn in case["turns"]
    )


def test_runner_loads_the_v6_dataset():
    dataset = load_dataset()
    assert dataset["dataset_id"] == "berlin-navigation-final-single-turn-scenarios-v6"
