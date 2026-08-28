import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chatbot import BVGAssistant

DEFAULT_SCENARIOS = (PROJECT_ROOT/"evaluation"/"conversation_scenarios_v1.json")
RESULTS = PROJECT_ROOT/"evaluation"/"results"


def load_scenarios(path: Path = DEFAULT_SCENARIOS) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def run_conversation(assistant: BVGAssistant, scenario: dict) -> dict:
    turns = []

    for turn_number, turn in enumerate(scenario["turns"], start=1):
        try:
            response = assistant.ask(turn["prompt"])
            sources = [
                {
                    "source": source.source,
                    "score": round(source.score, 4),
                    "category": source.category,
                }
                for source in response.sources
            ]
            turns.append(
                {
                    "turn": turn_number,
                    "prompt": turn["prompt"],
                    "expected_route": turn.get("expected_route"),
                    "expected_behavior": turn.get("expected_behavior"),
                    "actual_route": response.route,
                    "route_correct": (
                        turn.get("expected_route") is None
                        or turn["expected_route"] == response.route
                    ),
                    "answer": response.answer,
                    "sources": sources,
                    "guardrail_triggers": response.guardrail_triggers,
                    "guardrail_details": response.guardrail_details,
                    "error": None,
                }
            )
        except Exception as exc:
            turns.append(
                {
                    "turn": turn_number,
                    "prompt": turn["prompt"],
                    "expected_route": turn.get("expected_route"),
                    "expected_behavior": turn.get("expected_behavior"),
                    "actual_route": None,
                    "route_correct": False,
                    "answer": None,
                    "sources": [],
                    "guardrail_triggers": [],
                    "guardrail_details": {},
                    "error": repr(exc),
                }
            )
            break

    return {
        "id": scenario["id"],
        "category": scenario["category"],
        "description": scenario["description"],
        "turns": turns,
    }


def run_scenarios(
    path: Path = DEFAULT_SCENARIOS,
    configuration: str = "baseline",
) -> list[dict]:
    scenarios = load_scenarios(path)
    results = []

    print(f"Running {len(scenarios)} multi-turn scenarios\n")
    for index, scenario in enumerate(scenarios, start=1):
        print(
            f"[{index:02}/{len(scenarios)}] {scenario['id']} "
            f"({scenario['category']})"
        )
        result = run_conversation(
            BVGAssistant(
                guarded=configuration == "guarded",
                enable_injection_guard=configuration == "injection",
                enable_completeness_guard=(
                    configuration == "completeness"
                ),
            ),
            scenario,
        )
        results.append(result)
        for turn in result["turns"]:
            print(
                f"  turn {turn['turn']}: route={turn['actual_route']} "
                f"route_correct={turn['route_correct']}"
            )
            if turn["error"]:
                print(f"  ERROR: {turn['error']}")

    return results


def save_results(results: list[dict], configuration: str) -> tuple[Path, Path]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS / f"{configuration}_conversations_v1.json"
    markdown_path = RESULTS / f"{configuration}_conversations_v1.md"
    generated_at = datetime.now().isoformat()

    payload = {
        "configuration": configuration,
        "dataset": "conversation_scenarios_v1",
        "run_at": generated_at,
        "scenario_count": len(results),
        "results": results,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# Multi-turn evaluation — {configuration}",
        "",
        "Dataset: `conversation_scenarios_v1`  ",
        f"Conversations: {len(results)}  ",
        f"Generated: {generated_at}",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result['id']} — {result['category']}",
                "",
                result["description"],
                "",
            ]
        )
        for turn in result["turns"]:
            lines.extend(
                [
                    f"### Turn {turn['turn']}",
                    "",
                    f"**User:** {turn['prompt']}",
                    "",
                    f"**Expected:** {turn['expected_behavior']}",
                    "",
                    f"**Route:** `{turn['actual_route']}` "
                    f"(expected `{turn['expected_route']}`)",
                    "",
                    f"**Assistant:** {turn['answer'] or '(no answer)'}",
                    "",
                ]
            )
            if turn["guardrail_triggers"]:
                lines.extend(
                    [
                        "**Guardrail triggers:** "
                        + ", ".join(turn["guardrail_triggers"]),
                        "",
                    ]
                )
            if turn["error"]:
                lines.extend([f"**Error:** `{turn['error']}`", ""])
        lines.extend(["---", ""])

    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--configuration",
        choices=("baseline", "completeness", "injection", "guarded"),
        default="baseline",
    )
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    args = parser.parse_args()

    results = run_scenarios(args.scenarios, args.configuration)
    json_path, markdown_path = save_results(results, args.configuration)

    total_turns = sum(len(result["turns"]) for result in results)
    correct_routes = sum(
        turn["route_correct"]
        for result in results
        for turn in result["turns"]
    )
    errors = sum(
        turn["error"] is not None
        for result in results
        for turn in result["turns"]
    )
    print(
        f"\nSummary: {correct_routes}/{total_turns} routes correct; "
        f"{errors} errors"
    )
    print(f"Saved:\n{json_path}\n{markdown_path}")


if __name__ == "__main__":
    main()
