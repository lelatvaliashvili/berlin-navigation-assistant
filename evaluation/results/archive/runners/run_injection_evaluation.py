import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chatbot import BVGAssistant


SCENARIOS_PATH = PROJECT_ROOT / "evaluation" / "scenarios_v1.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
INJECTION_TRIGGER = "prompt_injection_authority"
INJECTION_CATEGORIES = {"prompt_injection", "benign_instruction"}


def load_scenarios() -> list[dict]:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as file:
        scenarios = json.load(file)

    return [
        scenario
        for scenario in scenarios
        if scenario["category"] in INJECTION_CATEGORIES
    ]


def serialize_response(response) -> dict:
    return {
        "route": response.route,
        "answer": response.answer,
        "guardrail_triggers": response.guardrail_triggers,
        "guardrail_details": response.guardrail_details,
    }


def safe_ask(assistant, prompt, decision) -> dict:
    try:
        response = assistant.ask(
            prompt,
            decision=decision.model_copy(deep=True),
        )
        return {**serialize_response(response), "error": None}
    except Exception as exc:
        return {
            "route": None,
            "answer": None,
            "guardrail_triggers": [],
            "guardrail_details": {},
            "error": repr(exc),
        }


def run_evaluation() -> list[dict]:
    scenarios = load_scenarios()
    results = []

    print(f"Running {len(scenarios)} paired injection scenarios\n")
    for index, scenario in enumerate(scenarios, start=1):
        baseline = BVGAssistant()
        injection_guarded = BVGAssistant(enable_injection_guard=True)

        # Both configurations receive the same route and extracted facts.
        shared_decision = baseline.classify(scenario["prompt"])
        baseline_result = safe_ask(
            baseline,
            scenario["prompt"],
            shared_decision,
        )
        guarded_result = safe_ask(
            injection_guarded,
            scenario["prompt"],
            shared_decision,
        )

        expected_trigger = scenario["category"] == "prompt_injection"
        actual_trigger = (
            INJECTION_TRIGGER in guarded_result["guardrail_triggers"]
        )
        result = {
            "id": scenario["id"],
            "category": scenario["category"],
            "prompt": scenario["prompt"],
            "expected_behavior": scenario["expected_behavior"],
            "expected_trigger": expected_trigger,
            "actual_trigger": actual_trigger,
            "trigger_correct": expected_trigger == actual_trigger,
            "shared_classification": shared_decision.model_dump(mode="json"),
            "baseline": baseline_result,
            "injection_guarded": guarded_result,
        }
        results.append(result)

        print(
            f"[{index:02}/{len(scenarios)}] {scenario['id']} "
            f"expected={expected_trigger} actual={actual_trigger}"
        )

    return results


def calculate_metrics(results: list[dict]) -> dict:
    true_positive = sum(
        result["expected_trigger"] and result["actual_trigger"]
        for result in results
    )
    false_positive = sum(
        not result["expected_trigger"] and result["actual_trigger"]
        for result in results
    )
    false_negative = sum(
        result["expected_trigger"] and not result["actual_trigger"]
        for result in results
    )
    true_negative = sum(
        not result["expected_trigger"] and not result["actual_trigger"]
        for result in results
    )
    expected_positives = true_positive + false_negative
    predicted_positives = true_positive + false_positive
    expected_negatives = true_negative + false_positive

    return {
        "case_count": len(results),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "trigger_recall": (
            true_positive / expected_positives
            if expected_positives
            else None
        ),
        "trigger_precision": (
            true_positive / predicted_positives
            if predicted_positives
            else None
        ),
        "false_positive_rate": (
            false_positive / expected_negatives
            if expected_negatives
            else None
        ),
        "baseline_errors": sum(
            result["baseline"]["error"] is not None
            for result in results
        ),
        "guarded_errors": sum(
            result["injection_guarded"]["error"] is not None
            for result in results
        ),
    }


def save_results(results: list[dict], metrics: dict) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "injection_focused_v1.json"
    markdown_path = RESULTS_DIR / "injection_focused_v1.md"
    run_at = datetime.now().isoformat()
    payload = {
        "dataset": "scenarios_v1_injection_and_benign_controls",
        "run_at": run_at,
        "metrics": metrics,
        "results": results,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Focused prompt-injection evaluation",
        "",
        "Paired baseline versus injection-only execution.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
        lines.append(f"| {key} | {rendered} |")

    for result in results:
        lines.extend(
            [
                "",
                f"## {result['id']} — {result['category']}",
                "",
                f"**User:** {result['prompt']}",
                "",
                f"**Expected trigger:** `{result['expected_trigger']}`",
                "",
                f"**Actual trigger:** `{result['actual_trigger']}`",
                "",
                f"**Baseline:** {result['baseline']['answer'] or '(no answer)'}",
                "",
                "**Injection guarded:** "
                f"{result['injection_guarded']['answer'] or '(no answer)'}",
            ]
        )

    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    results = run_evaluation()
    metrics = calculate_metrics(results)
    json_path, markdown_path = save_results(results, metrics)

    print("\nMetrics")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    print(f"\nSaved:\n{json_path}\n{markdown_path}")


if __name__ == "__main__":
    main()
