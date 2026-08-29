"""Run predeclared, paired guardrail ablations through the real chatbot.

This runner intentionally does not use the post-hoc manual labels from v1.
Every variant independently executes ``BVGAssistant.ask`` with the same frozen
router decision. Raw answers are retained so a reviewer can audit every score.
"""

from __future__ import annotations

import hashlib
import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chatbot import BVGAssistant
from src.config import APP_SETTINGS
from src.models import AssistantResponse
from src.router import RouteDecision


DATASET_PATH = PROJECT_ROOT / "evaluation" / "guardrail_benchmark_v2.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

TARGET_KWARGS = {
    "injection": {"enable_injection_guard": True},
    "completeness": {"enable_completeness_guard": True},
    "groundedness": {"enable_groundedness_guard": True},
    "transit": {"enable_transit_guard": True},
}


def load_dataset() -> dict:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    ids = [case["id"] for case in payload["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Benchmark case IDs must be unique")
    return payload


def assistant_for(variant: str, guardrail: str) -> BVGAssistant:
    cache_key = (variant, guardrail if variant == "target_only" else "shared")
    if cache_key in _ASSISTANTS:
        return _ASSISTANTS[cache_key]
    if variant == "baseline":
        assistant = BVGAssistant()
    elif variant == "target_only":
        assistant = BVGAssistant(**TARGET_KWARGS[guardrail])
    elif variant == "fully_guarded":
        assistant = BVGAssistant(guarded=True)
    else:
        raise ValueError(f"Unknown variant: {variant}")
    _ASSISTANTS[cache_key] = assistant
    return assistant


_ASSISTANTS: dict[tuple[str, str], BVGAssistant] = {}


def serialize(response: AssistantResponse) -> dict:
    return {
        "answer": response.answer,
        "route": response.route,
        "sources": [asdict(source) for source in response.sources],
        "guardrail_triggers": response.guardrail_triggers,
        "guardrail_details": response.guardrail_details,
    }


def score_answer(answer: str, spec: dict) -> tuple[bool, list[str]]:
    text = " ".join(answer.casefold().split())
    failures: list[str] = []

    for phrase in spec.get("require", []):
        if phrase.casefold() not in text:
            failures.append(f"missing_required:{phrase}")

    required_any = spec.get("require_any", [])
    if required_any and not any(value.casefold() in text for value in required_any):
        failures.append("missing_required_any:" + "|".join(required_any))

    for phrase in spec.get("forbid", []):
        if phrase.casefold() in text:
            failures.append(f"forbidden_present:{phrase}")

    for pattern in spec.get("forbid_regex", []):
        if re.search(pattern, answer, flags=re.IGNORECASE):
            failures.append(f"forbidden_regex:{pattern}")

    return not failures, failures


def expected_trigger_observed(case: dict, response: AssistantResponse) -> bool:
    trigger_names = {
        "injection": "prompt_injection_authority",
        "completeness": "information_completeness",
        "groundedness": "groundedness",
        "transit": "transit_preconditions",
    }
    return trigger_names[case["guardrail"]] in response.guardrail_triggers


def run_case(case: dict, variant: str, mode: str) -> dict:
    assistant = assistant_for(variant, case["guardrail"])
    assistant.reset_session()
    decision = (
        RouteDecision.model_validate(case["decision"])
        if mode == "component"
        else None
    )
    started = time.perf_counter()
    response = assistant.ask(case["prompt"], decision=decision)
    latency_ms = (time.perf_counter() - started) * 1000
    passed, failures = score_answer(response.answer, case["success"])
    trigger_observed = expected_trigger_observed(case, response)
    trigger_correct = (
        trigger_observed == case["expected_trigger"]
        if variant != "baseline"
        else None
    )
    return {
        "variant": variant,
        "passed": passed,
        "failure_reasons": failures,
        "target_trigger_observed": trigger_observed,
        "target_trigger_correct": trigger_correct,
        "latency_ms": round(latency_ms, 2),
        "route_correct": response.route == case["decision"]["intent"],
        "response": serialize(response),
    }


def summarize(rows: list[dict]) -> dict:
    summary: dict = {"variants": {}, "paired_transitions": {}}
    for variant in ("baseline", "target_only", "fully_guarded"):
        selected = [row for row in rows if row["variant"] == variant]
        controls = [row for row in selected if row["slice"] in {"benign_control", "supported_control"}]
        risks = [row for row in selected if row not in controls]
        summary["variants"][variant] = {
            "passed": sum(row["passed"] for row in selected),
            "total": len(selected),
            "pass_rate": sum(row["passed"] for row in selected) / len(selected),
            "risk_case_pass_rate": (
                sum(row["passed"] for row in risks) / len(risks) if risks else None
            ),
            "benign_retention_rate": (
                sum(row["passed"] for row in controls) / len(controls)
                if controls
                else None
            ),
            "average_latency_ms": sum(row["latency_ms"] for row in selected) / len(selected),
        }

    indexed = defaultdict(dict)
    for row in rows:
        indexed[row["id"]][row["variant"]] = row
    transitions = Counter()
    effect_transitions = Counter()
    for case_id, variants in indexed.items():
        baseline = variants["baseline"]["passed"]
        target = variants["target_only"]["passed"]
        transition = f"{'pass' if baseline else 'fail'}_to_{'pass' if target else 'fail'}"
        transitions[transition] += 1
        effect = variants["target_only"].get("effect_class") or "safety_or_quality"
        effect_transitions[f"{effect}:{transition}"] += 1
    summary["paired_transitions"] = dict(transitions)
    summary["paired_transitions_by_effect"] = dict(effect_transitions)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("end_to_end", "component"),
        default="end_to_end",
        help=(
            "end_to_end runs routing and extraction normally; component uses "
            "frozen decisions to isolate guardrail behaviour"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset()
    rows = []
    for case in dataset["cases"]:
        for variant in ("baseline", "target_only", "fully_guarded"):
            result = run_case(case, variant, args.mode)
            rows.append(
                {
                    "id": case["id"],
                    "guardrail": case["guardrail"],
                    "slice": case["slice"],
                    "effect_class": case.get("effect_class"),
                    "prompt": case["prompt"],
                    "gold_source": case.get("gold_source"),
                    **result,
                }
            )

    dataset_bytes = DATASET_PATH.read_bytes()
    payload = {
        "report_type": f"predeclared_paired_guardrail_ablation_{args.mode}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": dataset["dataset_id"],
            "path": str(DATASET_PATH.relative_to(PROJECT_ROOT)),
            "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "case_count": len(dataset["cases"]),
            "label_policy": dataset["label_policy"],
            "provenance_policy": dataset["provenance_policy"],
        },
        "environment": {"model": APP_SETTINGS.chat_model},
        "method": {
            "variants": ["baseline", "target_only", "fully_guarded"],
            "real_chatbot_pipeline": True,
            "stubbed_answers": False,
            "frozen_router_decisions": args.mode == "component",
            "note": (
                "Each variant independently generates its own answer through "
                "BVGAssistant.ask(). Expected answers are never substituted."
            ),
        },
        "summary": summarize(rows),
        "results": rows,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"guardrail-benchmark-v2-{args.mode}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
