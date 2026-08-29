import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_chatbot_ab_evaluation import save_results
from src.guardrails.groundedness import GroundednessGuard


RESULT_PATH = PROJECT_ROOT / "evaluation" / "results" / "chatbot_ab_v1.json"


def main() -> None:
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    results = payload["results"]
    guard = GroundednessGuard()

    for case in results["groundedness"]:
        started = time.perf_counter()
        baseline_answer = case["baseline"]["answer"]
        check = guard.check(
            question=case["prompt"],
            evidence=case["evidence"],
            answer=baseline_answer,
        )
        triggered = not check.supported
        case["guarded"] = {
            "answer": guard.fallback if triggered else baseline_answer,
            "route": "knowledge",
            "sources": case["baseline"]["sources"],
            "guardrail_triggers": ["groundedness"] if triggered else [],
            "guardrail_details": {
                "supported": check.supported,
                "unsupported_claims": check.unsupported_claims,
                "reason": check.reason,
            },
        }
        case["changed"] = triggered
        case["latency_seconds"] = time.perf_counter() - started

    json_path, markdown_path = save_results(results)
    print(f"Rejudged frozen chatbot candidates:\n{json_path}\n{markdown_path}")


if __name__ == "__main__":
    main()
