from src.guardrails.groundedness import (
    GroundedAnswerRepair,
    GroundednessDecision,
    GroundednessGuard,
)


class FakeJudge:
    def __init__(self, decision: GroundednessDecision) -> None:
        self.decision = decision

    def invoke(self, _messages):
        return self.decision


class FakeRepairer:
    def invoke(self, _messages):
        return GroundedAnswerRepair(
            answer="The reviewed source does not list that fare."
        )


def make_guard(decision: GroundednessDecision) -> GroundednessGuard:
    return GroundednessGuard(
        judge=FakeJudge(decision),
        repairer=FakeRepairer(),
    )


def test_unsupported_answer_is_rejected() -> None:
    guard = make_guard(
        GroundednessDecision(
            supported=False,
            unsupported_claims=["The invented fare."],
            reason="The evidence contains no fare.",
        )
    )

    result = guard.check(
        question="What is the fare?",
        evidence="The reviewed source does not list a fare.",
        answer="The fare is expensive.",
    )

    assert not result.supported
    assert result.unsupported_claims == ["The invented fare."]


def test_empty_evidence_fails_closed_without_judge() -> None:
    guard = make_guard(
        GroundednessDecision(supported=True, reason="unused")
    )

    result = guard.check(question="Question", evidence="", answer="Answer")

    assert not result.supported
    assert "No reviewed evidence" in result.unsupported_claims[0]


def test_number_absent_from_evidence_fails_before_judge() -> None:
    guard = make_guard(
        GroundednessDecision(supported=True, reason="unused")
    )

    result = guard.check(
        question="What is the monthly price?",
        evidence="The reviewed source does not list a monthly price.",
        answer="The monthly price is 72.50 EUR.",
    )

    assert not result.supported
    assert "72.50" in result.unsupported_claims[0]


def test_number_from_question_is_not_automatically_rejected() -> None:
    guard = make_guard(
        GroundednessDecision(
            supported=True,
            reason="The age is supported by the evidence range.",
        )
    )

    result = guard.check(
        question="Can my 7-year-old travel?",
        evidence="Children aged 6 to 14 are included.",
        answer="Yes, your 7-year-old is included.",
    )

    assert result.supported


def test_explicit_return_prohibition_allows_supported_transfer_claim() -> None:
    guard = make_guard(
        GroundednessDecision(
            supported=False,
            reason="The fake judge confuses transfers with returns.",
        )
    )

    result = guard.check(
        question="Can I make a return journey?",
        evidence=(
            "Transfers are permitted. Round trips and return journeys are "
            "not permitted."
        ),
        answer=(
            "A single ticket does not permit a return journey, although "
            "transfers are permitted."
        ),
    )

    assert result.supported


def test_repair_retains_a_specific_evidence_based_limitation() -> None:
    guard = make_guard(
        GroundednessDecision(supported=False, reason="Unsupported fare")
    )
    answer = guard.repair(
        question="What is the fare?",
        official_context="The reviewed source does not list the fare.",
        answer="It is EUR 99.",
        unsupported_claims=["EUR 99"],
    )
    assert answer == "The reviewed source does not list that fare."
