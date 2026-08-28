from src.guardrails.completeness import InformationCompletenessGuard
from src.models import ConversationState
from src.router import ConversationFacts, RouteDecision
from src.chatbot import BVGAssistant


def test_child_travel_requires_ticket_type_and_passenger_details() -> None:
    guard = InformationCompletenessGuard()
    result = guard.evaluate("child_travel",ConversationFacts())

    assert result.missing_fields == ["ticket_type", "passenger_details"]


def test_child_travel_passes_with_structured_facts() -> None:
    guard = InformationCompletenessGuard()
    result = guard.evaluate(
        "child_travel",
        ConversationFacts(
            ticket_type="24-hour ticket",
            passenger_details=["age 7"],
            travel_area="zones AB",
        ),
    )

    assert result.complete


def test_ticket_recommendation_uses_yaml_requirements() -> None:
    guard = InformationCompletenessGuard()
    result = guard.evaluate(
        "ticket_recommendation",
        {
            "passenger_details": [],
            "travel_area": None,
            "travel_period": "today",
            "journey_pattern": None,
        },
    )

    assert result.missing_fields == [
        "passenger_details",
        "travel_area",
        "journey_pattern",
    ]


def test_preclassified_decision_skips_second_router_call() -> None:
    assistant = BVGAssistant.__new__(BVGAssistant)
    assistant.state = ConversationState()
    assistant.injection_guard = None
    assistant.completeness_guard = InformationCompletenessGuard()

    class RouterThatMustNotRun:
        def route(self, _message):
            raise AssertionError("router was called a second time")

    assistant.router = RouterThatMustNotRun()
    decision = RouteDecision(
        intent="knowledge",
        request_type="child_travel",
        facts=ConversationFacts(),
        reasoning_summary="Incomplete child-travel request",
    )

    response = assistant.ask(
        "Can my daughter travel with me on this ticket?",
        decision=decision,
    )

    assert response.guardrail_triggers == ["information_completeness"]


def test_complete_request_is_not_silently_rerouted_by_guard() -> None:
    assistant = BVGAssistant.__new__(BVGAssistant)
    assistant.state = ConversationState()
    assistant.injection_guard = None
    assistant.completeness_guard = InformationCompletenessGuard()
    observed = {}

    def handle_journey(decision):
        observed["intent"] = decision.intent
        from src.models import AssistantResponse

        return AssistantResponse(answer="journey", route="journey")

    assistant._resolve_slots = lambda _decision, _question: None
    assistant._handle_journey = handle_journey
    decision = RouteDecision(
        intent="journey",
        request_type="child_travel",
        facts=ConversationFacts(
            ticket_type="24-hour ticket",
            passenger_details=["age 7"],
        ),
        reasoning_summary="Complete request",
    )

    response = assistant.ask("Complete request", decision=decision)

    assert response.route == "journey"
    assert observed["intent"] == "journey"
    assert response.guardrail_triggers == []
