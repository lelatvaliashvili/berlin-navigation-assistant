import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chatbot import BVGAssistant


SCENARIOS_PATH = (
    PROJECT_ROOT / "evaluation" / "completeness_scenarios_v1.json"
)
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def load_scenarios() -> list[dict]:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def serialize_response(response) -> dict:
    return {
        "route": response.route,
        "answer": response.answer,
        "guardrail_triggers": response.guardrail_triggers,
        "guardrail_details": response.guardrail_details,
    }


def safe_ask(
    assistant: BVGAssistant,
    prompt: str,
    decision=None,
) -> dict:
    try:
        return {
            **serialize_response(
                assistant.ask(prompt, decision=decision)
            ),
            "error": None,
        }
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

    print(f"Running {len(scenarios)} focused completeness scenarios\n")
    for index, scenario in enumerate(scenarios, start=1):
        print(f"[{index:02}/{len(scenarios)}] {scenario['id']}")
        baseline = BVGAssistant()
        guarded = BVGAssistant(enable_completeness_guard=True)
        turns = []

        for turn_number, turn in enumerate(scenario["turns"], start=1):
            # Classify once using the guarded conversation context, then give
            # each configuration an independent deep copy. This prevents two
            # nondeterministic router calls from contaminating the comparison.
            shared_decision = guarded.classify(turn["prompt"])
            baseline_result = safe_ask(
                baseline,
                turn["prompt"],
                shared_decision.model_copy(deep=True),
            )
            guarded_result = safe_ask(
                guarded,
                turn["prompt"],
                shared_decision.model_copy(deep=True),
            )
            actual_trigger = (
                "information_completeness"
                in guarded_result["guardrail_triggers"]
            )
            actual_missing = guarded_result["guardrail_details"].get(
                "missing_fields",
                [],
            )
            expected_missing = turn["expected_missing_fields"]

            turns.append(
                {
                    "turn": turn_number,
                    "prompt": turn["prompt"],
                    "expected_trigger": turn["expected_trigger"],
                    "expected_missing_fields": expected_missing,
                    "shared_classification": (
                        shared_decision.model_dump(mode="json")
                    ),
                    "follow_up_resolution": turn.get(
                        "follow_up_resolution",
                        False,
                    ),
                    "actual_trigger": actual_trigger,
                    "actual_missing_fields": actual_missing,
                    "trigger_correct": (
                        actual_trigger == turn["expected_trigger"]
                    ),
                    "missing_fields_correct": (
                        set(actual_missing) == set(expected_missing)
                    ),
                    "baseline": baseline_result,
                    "completeness_guarded": guarded_result,
                }
            )

            print(
                f"  turn {turn_number}: expected_trigger="
                f"{turn['expected_trigger']} actual_trigger={actual_trigger} "
                f"missing={actual_missing}"
            )

        results.append(
            {
                "id": scenario["id"],
                "category": scenario["category"],
                "description": scenario["description"],
                "turns": turns,
            }
        )

    return results


def calculate_metrics(results: list[dict]) -> dict:
    turns = [turn for result in results for turn in result["turns"]]
    true_positive = sum(
        turn["expected_trigger"] and turn["actual_trigger"]
        for turn in turns
    )
    false_positive = sum(
        not turn["expected_trigger"] and turn["actual_trigger"]
        for turn in turns
    )
    false_negative = sum(
        turn["expected_trigger"] and not turn["actual_trigger"]
        for turn in turns
    )
    true_negative = sum(
        not turn["expected_trigger"] and not turn["actual_trigger"]
        for turn in turns
    )

    positive_predictions = true_positive + false_positive
    expected_positives = true_positive + false_negative
    expected_negatives = true_negative + false_positive
    follow_ups = [turn for turn in turns if turn["follow_up_resolution"]]
    correct_missing = sum(
        turn["expected_trigger"] and turn["missing_fields_correct"]
        for turn in turns
    )

    return {
        "turn_count": len(turns),
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
            true_positive / positive_predictions
            if positive_predictions
            else None
        ),
        "false_positive_rate": (
            false_positive / expected_negatives
            if expected_negatives
            else None
        ),
        "correct_missing_field_rate": (
            correct_missing / expected_positives
            if expected_positives
            else None
        ),
        "follow_up_resolution_rate": (
            sum(
                not turn["actual_trigger"]
                and turn["completeness_guarded"]["route"] == "knowledge"
                for turn in follow_ups
            )
            / len(follow_ups)
            if follow_ups
            else None
        ),
        "baseline_errors": sum(
            turn["baseline"]["error"] is not None
            for turn in turns
        ),
        "guarded_errors": sum(
            turn["completeness_guarded"]["error"] is not None
            for turn in turns
        ),
    }


def save_results(results: list[dict], metrics: dict) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "completeness_focused_v1.json"
    markdown_path = RESULTS_DIR / "completeness_focused_v1.md"
    run_at = datetime.now().isoformat()
    payload = {
        "dataset": "completeness_scenarios_v1",
        "run_at": run_at,
        "scenario_count": len(results),
        "metrics": metrics,
        "results": results,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Focused completeness evaluation",
        "",
        f"Generated: {run_at}",
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
                result["description"],
            ]
        )
        for turn in result["turns"]:
            lines.extend(
                [
                    "",
                    f"### Turn {turn['turn']}",
                    "",
                    f"**User:** {turn['prompt']}",
                    "",
                    f"**Expected trigger:** `{turn['expected_trigger']}`",
                    "",
                    "**Expected missing fields:** "
                    f"`{turn['expected_missing_fields']}`",
                    "",
                    f"**Actual trigger:** `{turn['actual_trigger']}`",
                    "",
                    "**Actual missing fields:** "
                    f"`{turn['actual_missing_fields']}`",
                    "",
                    "**Baseline:** "
                    f"{turn['baseline']['answer'] or '(no answer)'}",
                    "",
                    "**Completeness guarded:** "
                    f"{turn['completeness_guarded']['answer'] or '(no answer)'}",
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
