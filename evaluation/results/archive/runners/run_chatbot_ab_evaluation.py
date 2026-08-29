import json
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chatbot import BVGAssistant
from src.guardrails.completeness import InformationCompletenessGuard
from src.guardrails.groundedness import GroundednessGuard
from src.guardrails.injection import PromptInjectionGuard
from src.guardrails.transit import TransitPreconditionGuard
from src.models import AssistantResponse
from src.router import RouteDecision


DATASET_PATH = PROJECT_ROOT / "evaluation" / "chatbot_ab_scenarios_v1.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def load_dataset() -> dict[str, list[dict]]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def decision_from(case: dict) -> RouteDecision:
    return RouteDecision.model_validate(case["decision"])


def serialize_response(response: AssistantResponse) -> dict:
    return {
        "answer": response.answer,
        "route": response.route,
        "sources": [
            {
                "source": source.source,
                "score": round(source.score, 4),
                "category": source.category,
            }
            for source in response.sources
        ],
        "guardrail_triggers": response.guardrail_triggers,
        "guardrail_details": response.guardrail_details,
    }


def baseline_answer(
    assistant: BVGAssistant,
    case: dict,
) -> AssistantResponse:
    assistant.reset_session()
    return assistant.ask(case["prompt"], decision=decision_from(case))


def evaluate_injection(
    assistant: BVGAssistant,
    cases: list[dict],
) -> list[dict]:
    guard = PromptInjectionGuard()
    results = []
    for case in cases:
        started = time.perf_counter()
        baseline = baseline_answer(assistant, case)
        check = guard.check(case["prompt"])
        guarded = (
            AssistantResponse(
                answer=guard.refusal,
                route="knowledge",
                guardrail_triggers=["prompt_injection_authority"],
                guardrail_details={"reason": check.reason},
            )
            if check.blocked
            else baseline
        )
        results.append(
            {
                **case,
                "baseline": serialize_response(baseline),
                "guarded": serialize_response(guarded),
                "changed": baseline.answer != guarded.answer,
                "latency_seconds": time.perf_counter() - started,
                "error": None,
            }
        )
    return results


def evaluate_completeness(
    assistant: BVGAssistant,
    cases: list[dict],
) -> list[dict]:
    guard = InformationCompletenessGuard()
    results = []
    for case in cases:
        started = time.perf_counter()
        decision = decision_from(case)
        baseline = baseline_answer(assistant, case)
        check = guard.evaluate(decision.request_type, decision.facts)
        triggered = check.applies and not check.complete
        guarded = (
            AssistantResponse(
                answer=guard.clarification(check),
                route="knowledge",
                guardrail_triggers=["information_completeness"],
                guardrail_details={
                    "request_type": check.request_type,
                    "missing_fields": check.missing_fields,
                },
            )
            if triggered
            else baseline
        )
        results.append(
            {
                **case,
                "baseline": serialize_response(baseline),
                "guarded": serialize_response(guarded),
                "changed": baseline.answer != guarded.answer,
                "latency_seconds": time.perf_counter() - started,
                "error": None,
            }
        )
    return results


def evidence_from(retrieved: list[tuple]) -> str:
    return "\n\n---\n\n".join(
        f"SOURCE: {document.metadata.get('source', 'unknown')}\n\n"
        f"{document.page_content}"
        for document, _score in retrieved
    )


def evaluate_groundedness(
    assistant: BVGAssistant,
    cases: list[dict],
) -> list[dict]:
    guard = GroundednessGuard()
    results = []
    for case in cases:
        started = time.perf_counter()
        assistant.reset_session()
        retrieved = assistant.retriever.retrieve(case["prompt"])
        original_retrieve = assistant.retriever.retrieve
        assistant.retriever.retrieve = lambda _query: retrieved
        try:
            baseline = assistant._handle_knowledge(case["prompt"])
        finally:
            assistant.retriever.retrieve = original_retrieve

        evidence = evidence_from(retrieved)
        check = guard.check(
            question=case["prompt"],
            evidence=evidence,
            answer=baseline.answer,
        )
        guarded = (
            AssistantResponse(
                answer=guard.fallback,
                route="knowledge",
                sources=baseline.sources,
                guardrail_triggers=["groundedness"],
                guardrail_details={
                    "supported": False,
                    "unsupported_claims": check.unsupported_claims,
                    "reason": check.reason,
                },
            )
            if not check.supported
            else AssistantResponse(
                answer=baseline.answer,
                route="knowledge",
                sources=baseline.sources,
                guardrail_details={
                    "supported": True,
                    "unsupported_claims": [],
                    "reason": check.reason,
                },
            )
        )
        results.append(
            {
                **case,
                "evidence": evidence,
                "baseline": serialize_response(baseline),
                "guarded": serialize_response(guarded),
                "changed": baseline.answer != guarded.answer,
                "latency_seconds": time.perf_counter() - started,
                "error": None,
            }
        )
    return results


def evaluate_transit(
    assistant: BVGAssistant,
    cases: list[dict],
) -> list[dict]:
    guard = TransitPreconditionGuard()
    results = []
    for case in cases:
        started = time.perf_counter()
        decision = decision_from(case)
        baseline = baseline_answer(assistant, case)
        check = guard.check(
            intent=decision.intent,
            origin=decision.origin,
            destination=decision.destination,
            station=decision.station,
        )
        triggered = check.applies and not check.complete
        guarded = (
            AssistantResponse(
                answer=guard.clarification(check),
                route=decision.intent,
                guardrail_triggers=["transit_preconditions"],
                guardrail_details={"missing_fields": check.missing_fields},
            )
            if triggered
            else baseline
        )
        results.append(
            {
                **case,
                "baseline": serialize_response(baseline),
                "guarded": serialize_response(guarded),
                "changed": baseline.answer != guarded.answer,
                "behavior_change": (
                    "observability_only"
                    if triggered and baseline.answer == guarded.answer
                    else "answer_changed"
                ),
                "latency_seconds": time.perf_counter() - started,
                "error": None,
            }
        )
    return results


def save_results(results: dict[str, list[dict]]) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now().isoformat()
    payload = {
        "dataset": "chatbot_ab_scenarios_v1",
        "run_at": run_at,
        "method": (
            "Baseline answers are generated once by chatbot.py. Groundedness "
            "judges that exact candidate and evidence; it does not regenerate."
        ),
        "results": results,
    }
    json_path = RESULTS_DIR / "chatbot_ab_v1.json"
    markdown_path = RESULTS_DIR / "chatbot_ab_v1.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Chatbot-generated A/B guardrail evaluation",
        "",
        f"Generated: {run_at}",
        "",
        payload["method"],
        "",
    ]
    for guard_name, cases in results.items():
        lines.extend([f"## {guard_name.replace('_', ' ').title()}", ""])
        for case in cases:
            triggers = ", ".join(case["guarded"]["guardrail_triggers"]) or "none"
            lines.extend(
                [
                    f"### {case['id']}",
                    "",
                    f"**Danger:** {case['danger']}",
                    "",
                    f"**Prompt:** {case['prompt']}",
                    "",
                    f"**Baseline:** {case['baseline']['answer']}",
                    "",
                    f"**Guarded:** {case['guarded']['answer']}",
                    "",
                    f"**Triggered:** {triggers}",
                    "",
                    f"**Why:** {case['guarded']['guardrail_details']}",
                    "",
                ]
            )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    dataset = load_dataset()
    assistant = BVGAssistant()
    results = {
        "injection": evaluate_injection(assistant, dataset["injection"]),
        "completeness": evaluate_completeness(
            assistant, dataset["completeness"]
        ),
        "groundedness": evaluate_groundedness(
            assistant, dataset["groundedness"]
        ),
        "transit_preconditions": evaluate_transit(
            assistant, dataset["transit_preconditions"]
        ),
    }
    json_path, markdown_path = save_results(results)
    print(f"Saved:\n{json_path}\n{markdown_path}")


if __name__ == "__main__":
    main()
