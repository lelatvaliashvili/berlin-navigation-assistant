"""Run the final multi-turn scenarios through baseline and guarded chatbots."""

from __future__ import annotations

import json
import argparse
import hashlib
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_benchmark import (
    SEMANTIC_JUDGE_PROMPT,
    SemanticVerdict,
    score_answer,
    serialize,
)
from src.chatbot import BVGAssistant
from src.llm import create_chat_model


DATASET_PATH = PROJECT_ROOT / "evaluation" / "multi_turn_benchmark.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def judge_turn(judge, case: dict, turn_number: int, baseline: dict, guarded: dict) -> dict:
    swap = int(hashlib.sha256(
        f"{case['id']}:{turn_number}".encode()
    ).hexdigest(), 16) % 2 == 1
    answer_a = guarded["response"]["answer"] if swap else baseline["response"]["answer"]
    answer_b = baseline["response"]["answer"] if swap else guarded["response"]["answer"]
    history = [turn["prompt"] for turn in case["turns"][:turn_number]]
    verdict = judge.invoke([
        ("system", SEMANTIC_JUDGE_PROMPT),
        ("user", json.dumps({
            "conversation_history_and_current_turn": history,
            "risk_type": case["category"],
            "policy_rubric": case["turns"][turn_number - 1]["success"],
            "answer_a": answer_a,
            "answer_b": answer_b,
        }, ensure_ascii=False)),
    ])
    safe = {
        "baseline": verdict.answer_b_safe if swap else verdict.answer_a_safe,
        "fully_guarded": verdict.answer_a_safe if swap else verdict.answer_b_safe,
    }
    return {
        "baseline_safe": safe["baseline"],
        "fully_guarded_safe": safe["fully_guarded"],
        "guarded_improves": safe["fully_guarded"] and not safe["baseline"],
        "guarded_regresses": safe["baseline"] and not safe["fully_guarded"],
        "confidence": verdict.confidence,
        "reason": verdict.reason,
    }


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
                "route_decision": (
                    assistant.last_decision.model_dump()
                    if assistant.last_decision is not None
                    else None
                ),
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Run a blinded semantic judge for every conversation turn.",
    )
    args = parser.parse_args()
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    total = len(dataset["cases"]) * 2
    completed = 0
    print(f"Running {total} conversation evaluations...", flush=True)
    results = []
    for case in dataset["cases"]:
        for variant in ("baseline", "fully_guarded"):
            result = run_conversation(case, variant)
            results.append(result)
            completed += 1
            print(
                f"[{completed}/{total}] {variant}: {case['id']} "
                f"({len(case['turns'])} turns)",
                flush=True,
            )
    summary = {}
    for variant in ("baseline", "fully_guarded"):
        selected = [row for row in results if row["variant"] == variant]
        summary[variant] = {
            "conversations_passed": sum(row["passed"] for row in selected),
            "conversations_total": len(selected),
        }

    semantic_judge = None
    if args.judge:
        judge = create_chat_model(num_predict=220).with_structured_output(
            SemanticVerdict
        )
        grouped = {}
        for row in results:
            grouped.setdefault(row["id"], {})[row["variant"]] = row
        turn_results = []
        for case in dataset["cases"]:
            pair = grouped[case["id"]]
            for turn_number in range(1, len(case["turns"]) + 1):
                baseline_turn = pair["baseline"]["turns"][turn_number - 1]
                guarded_turn = pair["fully_guarded"]["turns"][turn_number - 1]
                turn_results.append({
                    "id": case["id"],
                    "turn": turn_number,
                    **judge_turn(judge, case, turn_number, baseline_turn, guarded_turn),
                })
        conversation_results = []
        for case in dataset["cases"]:
            turns = [r for r in turn_results if r["id"] == case["id"]]
            baseline_safe = all(r["baseline_safe"] for r in turns)
            guarded_safe = all(r["fully_guarded_safe"] for r in turns)
            conversation_results.append({
                "id": case["id"],
                "baseline_safe": baseline_safe,
                "fully_guarded_safe": guarded_safe,
                "guarded_improves": guarded_safe and not baseline_safe,
                "guarded_regresses": baseline_safe and not guarded_safe,
            })
        semantic_judge = {
            "turns": len(turn_results),
            "baseline_safe": sum(r["baseline_safe"] for r in turn_results),
            "guarded_safe": sum(r["fully_guarded_safe"] for r in turn_results),
            "guarded_improves": sum(r["guarded_improves"] for r in turn_results),
            "guarded_regresses": sum(r["guarded_regresses"] for r in turn_results),
            "results": turn_results,
            "conversation_results": conversation_results,
            "conversations_baseline_safe": sum(
                r["baseline_safe"] for r in conversation_results
            ),
            "conversations_guarded_safe": sum(
                r["fully_guarded_safe"] for r in conversation_results
            ),
            "conversations_guarded_improves": sum(
                r["guarded_improves"] for r in conversation_results
            ),
        }

    payload = {
        "report_type": "multi_turn_baseline_vs_fully_guarded",
        "dataset": dataset["dataset_id"],
        "summary": summary,
        "results": results,
        **({"semantic_judge": semantic_judge} if semantic_judge else {}),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "benchmark-multi-turn-conversations.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
