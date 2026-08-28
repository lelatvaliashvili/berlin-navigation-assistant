"""Run the four multi-turn conversations through baseline and guarded chatbots."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_benchmark import score_answer, serialize
from src.chatbot import BVGAssistant


DATASET_PATH = PROJECT_ROOT / "evaluation" / "conversation_benchmark.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def run_conversation(case: dict, variant: str) -> dict:
    assistant = BVGAssistant(guarded=variant == "fully_guarded")
    turns = []
    for turn_number, turn in enumerate(case["turns"], start=1):
        started = time.perf_counter()
        response = assistant.ask(turn["prompt"])
        latency_ms = (time.perf_counter() - started) * 1000
        passed, failures = score_answer(response.answer, turn["success"])
        turns.append(
            {
                "turn": turn_number,
                "prompt": turn["prompt"],
                "passed": passed,
                "failure_reasons": failures,
                "latency_ms": round(latency_ms, 2),
                "response": serialize(response),
            }
        )
    return {
        "id": case["id"],
        "category": case["category"],
        "variant": variant,
        "passed": all(turn["passed"] for turn in turns),
        "turns": turns,
    }


def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    results = [
        run_conversation(case, variant)
        for case in dataset["cases"]
        for variant in ("baseline", "fully_guarded")
    ]
    summary = {}
    for variant in ("baseline", "fully_guarded"):
        selected = [row for row in results if row["variant"] == variant]
        summary[variant] = {
            "conversations_passed": sum(row["passed"] for row in selected),
            "conversations_total": len(selected),
        }

    payload = {
        "report_type": "multi_turn_baseline_vs_fully_guarded",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset["dataset_id"],
        "summary": summary,
        "results": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"benchmark-conversations-{stamp}.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
