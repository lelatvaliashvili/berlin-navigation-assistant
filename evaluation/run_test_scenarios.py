import json
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
from src.chatbot import BVGAssistant


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCENARIOS = (PROJECT_ROOT / "evaluation" / "scenarios_v1.json")

RESULTS = (PROJECT_ROOT / "evaluation" / "results")


def load_scenarios(
    path: Path = DEFAULT_SCENARIOS,
) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def run_scenario(
    assistant: BVGAssistant,
    scenario: dict,
) -> dict:

    try:
        response = assistant.ask(
            scenario["prompt"]
        )
        sources = [
            {
                "source": source.source,
                "score": round(source.score, 4),
                "category": source.category,
            }
            for source in response.sources
        ]

        return {
            "id": scenario["id"],
            "category": scenario["category"],
            "prompt": scenario["prompt"],
            "expected_route": scenario.get(
                "expected_route"
            ),
            "expected_behavior": scenario.get(
                "expected_behavior"
            ),
            "actual_route": response.route,
            "answer": response.answer,
            "sources": sources,
            "error": None,
        }

    except Exception as exc:
        return {
            "id": scenario["id"],
            "category": scenario["category"],
            "prompt": scenario["prompt"],
            "expected_route": scenario.get(
                "expected_route"
            ),
            "expected_behavior": scenario.get(
                "expected_behavior"
            ),

            "actual_route": None,
            "answer": None,
            "sources": [],
            "error": repr(exc),
        }

def run_scenarios(configuration: str = "baseline",
    scenarios_path: Path = DEFAULT_SCENARIOS) -> list[dict]:
    scenarios = load_scenarios(scenarios_path)
    results = []

    print(f"\nRunning {len(scenarios)} scenarios " )

    for index, scenario in enumerate(scenarios, start=1,):
        assistant = BVGAssistant()
        print(
            f"[{index:02}/{len(scenarios)}] "
            f"{scenario['id']} "
            f"({scenario['category']})"
        )

        result = run_scenario(assistant, scenario)
        results.append(result)

        print(f"Route={result['actual_route']} ")

        if result["error"]:
            print(f"ERROR: {result['error']}")

    return results


def results_to_dataframe(
    results: list[dict],
) -> pd.DataFrame:

    rows = []

    for result in results:

        expected_route = result[
            "expected_route"
        ]

        actual_route = result[
            "actual_route"
        ]

        route_correct = (
            expected_route is None
            or expected_route == actual_route
        )

        source_names = ", ".join(
            source["source"]
            for source in result["sources"]
        )

        rows.append(
            {
                "id": result["id"],
                "category": result["category"],
                "expected_route": expected_route,
                "actual_route": actual_route,
                "route_correct": route_correct,
                "sources": source_names,
                "error": result["error"],
                "answer": result["answer"],
            }
        )

    return pd.DataFrame(rows)


def save_json_results(
    results: list[dict],
    configuration: str,
) -> Path:

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
            RESULTS
            / f"{configuration}_v1.json"
    )

    payload = {
        "configuration": configuration,
        "dataset": "scenarios_v1",
        "run_at": datetime.now().isoformat(),
        "scenario_count": len(results),
        "results": results,
    }

    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False,),  encoding="utf-8",)
    return output_path


def save_markdown_report(
    results: list[dict],
    configuration: str,
) -> Path:

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
            RESULTS
            / f"{configuration}_v1.md"
    )

    lines = [
        f"# Evaluation — {configuration}",
        "",
        f"Dataset: `scenarios_v1`  ",
        f"Cases: {len(results)}  ",
        f"Generated: {datetime.now().isoformat()}",
        "",
    ]

    for result in results:

        lines.extend(
            [
                f"## {result['id']}",
                "",
                f"**Category:** {result['category']}",
                "",
                "**Prompt**",
                "",
                f"> {result['prompt']}",
                "",
                "**Expected behavior**",
                "",
                result["expected_behavior"],
                "",
                f"**Expected route:** "
                f"`{result['expected_route']}`",
                "",
                f"**Actual route:** "
                f"`{result['actual_route']}`",
                "",
                "",
                "**Answer**",
                "",
                result["answer"] or "(no answer)",
                "",
            ]
        )

        if result["sources"]:

            lines.append(
                "**Retrieved sources**"
            )

            lines.append("")

            for source in result["sources"]:
                lines.append(
                    f"- `{source['source']}` "
                    f"(score={source['score']})"
                )

            lines.append("")

        if result["error"]:

            lines.extend(
                [
                    "**Error**",
                    "",
                    f"`{result['error']}`",
                    "",
                ]
            )

        lines.append("---")
        lines.append("")

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return output_path


def save_results(
    results: list[dict],
    configuration: str,
) -> tuple[Path, Path]:

    json_path = save_json_results(
        results,
        configuration,
    )

    markdown_path = save_markdown_report(
        results,
        configuration,
    )

    return json_path, markdown_path


def main() -> None:

    configuration = "baseline"

    results = run_scenarios(
        configuration=configuration
    )

    json_path, markdown_path = save_results(
        results,
        configuration,
    )

    dataframe = results_to_dataframe(
        results
    )

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        dataframe[
            [
                "id",
                "category",
                "actual_route",
                "route_correct",
            ]
        ].to_string(index=False)
    )

    print("\nSaved:")
    print(json_path)
    print(markdown_path)


if __name__ == "__main__":
    main()