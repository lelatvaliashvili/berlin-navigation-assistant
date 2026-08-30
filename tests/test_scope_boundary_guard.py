import pytest
from pydantic import ValidationError

from src.chatbot import BVGAssistant
from src.guardrails.scope_boundary import ScopeBoundaryGuard, ScopeDecision
from src.models import AssistantResponse, ConversationState
from src.router import ConversationFacts, RouteDecision


class StaticScopeClassifier:
    def __init__(self, decision: ScopeDecision) -> None:
        self.decision = decision
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return self.decision


def guard_for(decision: ScopeDecision) -> ScopeBoundaryGuard:
    return ScopeBoundaryGuard(StaticScopeClassifier(decision))


def test_scope_is_required_in_structured_scope_decision() -> None:
    with pytest.raises(ValidationError):
        ScopeDecision()


def test_incomplete_mixed_scope_fails_closed_without_parser_error() -> None:
    decision = ScopeDecision(status="mixed")
    assert decision.status == "out_of_scope"


def test_out_of_scope_decision_allows_generic_topic_fallback() -> None:
    guard = guard_for(ScopeDecision(status="out_of_scope"))
    check = guard.check("Tell me something unrelated")
    assert "official source" in guard.refusal(check)


def test_missing_topic_label_uses_request_for_helpful_redirect() -> None:
    guard = guard_for(
        ScopeDecision(
            status="out_of_scope",
            boundary_message=(
                "I specialize in Berlin public transport. Please check a "
                "current events source for that request."
            ),
        )
    )
    check = guard.check("Which concerts are on this weekend?")
    assert "current events source" in guard.refusal(check)


def test_accessibility_question_is_not_rejected_as_out_of_scope() -> None:
    guard = guard_for(ScopeDecision(status="in_scope"))
    check = guard.check("Is the elevator at Alexanderplatz working?")
    assert check.status == "in_scope"


def test_scope_response_uses_structured_contextual_message() -> None:
    guard = guard_for(
        ScopeDecision(
            status="out_of_scope",
            out_of_scope_topics=["Hamburg public transport"],
            boundary_message=(
                "I specialize in Berlin public transport. Please check the "
                "official local transport provider for current fares."
            ),
        )
    )
    check = guard.check("What ticket should I buy in Hamburg?")
    assert check.applies
    assert "official local transport provider" in guard.refusal(check)


def test_concert_scope_response_offers_transport_help() -> None:
    guard = guard_for(
        ScopeDecision(
            status="out_of_scope",
            out_of_scope_topics=["current concert recommendations"],
            boundary_message=(
                "I specialize in Berlin public transport. Please check a "
                "current event source, and I can help with the journey."
            ),
        )
    )
    response = guard.refusal(guard.check("Recommend a concert"))
    assert "current event source" in response
    assert "help with the journey" in response


@pytest.mark.integration
def test_out_of_scope_request_stops_before_generation() -> None:
    assistant = BVGAssistant.__new__(BVGAssistant)
    assistant.state = ConversationState()
    assistant.injection_guard = None
    assistant.scope_guard = guard_for(
        ScopeDecision(
            status="out_of_scope",
            out_of_scope_topics=["current concert recommendations"],
            boundary_message=(
                "I specialize in Berlin public transport. Please check a "
                "current event source."
            ),
        )
    )

    class RouterThatMustNotRun:
        def route(self, _message):
            raise AssertionError("router ran after a scope rejection")

    assistant.router = RouterThatMustNotRun()
    decision = RouteDecision(
        intent="other",
        facts=ConversationFacts(),
        reasoning_summary="Unsupported request",
    )
    response = assistant.ask("Recommend a concert", decision=decision)
    assert response.guardrail_triggers == ["scope_boundary"]
    assert response.route == "other"
    assert "current event source" in response.answer


def test_scope_classifier_receives_structured_intercity_endpoints() -> None:
    classifier = StaticScopeClassifier(
        ScopeDecision(
            status="out_of_scope",
            boundary_message="I can only help with Berlin public transport.",
        )
    )
    guard = ScopeBoundaryGuard(classifier)

    check = guard.check(
        "How long does it take to get there?",
        intent="journey",
        origin="Berlin",
        destination="Munich",
    )

    payload = classifier.messages[-1][1]
    assert "intent: journey" in payload
    assert "origin: Berlin" in payload
    assert "destination: Munich" in payload
    assert check.status == "out_of_scope"


@pytest.mark.integration
def test_intercity_scope_rejection_stops_before_journey_tool() -> None:
    assistant = BVGAssistant.__new__(BVGAssistant)
    assistant.state = ConversationState()
    assistant.injection_guard = None
    assistant.scope_guard = guard_for(
        ScopeDecision(
            status="out_of_scope",
            out_of_scope_topics=["Berlin to Munich intercity journey"],
            boundary_message=(
                "I specialize in Berlin public transport and can't reliably "
                "plan that intercity journey."
            ),
        )
    )
    journey_called = False

    def handle_journey(_decision) -> AssistantResponse:
        nonlocal journey_called
        journey_called = True
        return AssistantResponse(answer="unexpected", route="journey")

    assistant._handle_journey = handle_journey
    decision = RouteDecision(
        intent="journey",
        origin="Berlin",
        destination="Munich",
        facts=ConversationFacts(),
        reasoning_summary="Berlin to Munich journey",
    )

    response = assistant.ask(
        "How much time will I need to get to Munich from Berlin?",
        decision=decision,
    )

    assert not journey_called
    assert response.guardrail_triggers == ["scope_boundary"]
    assert "intercity journey" in response.answer


@pytest.mark.integration
def test_mixed_request_answers_only_supported_part_and_adds_redirect() -> None:
    assistant = BVGAssistant.__new__(BVGAssistant)
    assistant.state = ConversationState()
    assistant.injection_guard = None
    assistant.completeness_guard = None
    assistant.groundedness_guard = None
    assistant.tool_grounding_guard = None
    assistant.scope_guard = guard_for(
        ScopeDecision(
            status="mixed",
            in_scope_request="What does a Berlin AB single ticket cost?",
            out_of_scope_topics=["Hamburg public transport"],
            boundary_message=(
                "For the unsupported portion, please check the appropriate "
                "official local transport source."
            ),
        )
    )
    assistant._resolve_slots = lambda _decision, _question: None
    observed = {}

    def handle_knowledge(question: str) -> AssistantResponse:
        observed["question"] = question
        return AssistantResponse(
            answer="A Berlin AB single ticket costs EUR 4.00.",
            route="knowledge",
        )

    assistant._handle_knowledge = handle_knowledge
    decision = RouteDecision(
        intent="knowledge",
        facts=ConversationFacts(),
        reasoning_summary="Berlin fare question",
    )

    class StaticRouter:
        def route(self, _message):
            return decision

    assistant.router = StaticRouter()
    response = assistant.ask(
        "What does a single ticket cost in Berlin and Hamburg?",
        decision=decision,
    )
    assert observed["question"] == "What does a Berlin AB single ticket cost?"
    assert "EUR 4.00" in response.answer
    assert "official local transport source" in response.answer
    assert response.guardrail_triggers == ["scope_boundary"]
