from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from src.llm import create_chat_model


class ScopeDecision(BaseModel):
    status: Literal["in_scope", "mixed", "out_of_scope"]
    in_scope_request: str | None = None
    out_of_scope_topics: list[str] = Field(default_factory=list)
    boundary_message: str | None = Field(
        default=None,
        description=(
            "Friendly user-facing boundary response for out-of-scope requests, "
            "or a short notice for the unsupported part of mixed requests."
        ),
    )

    @model_validator(mode="after")
    def fail_closed_on_incomplete_mixed_result(self):
        if self.status == "mixed" and not self.in_scope_request:
            self.status = "out_of_scope"
        if self.status != "in_scope" and not self.boundary_message:
            self.boundary_message = (
                "I can help with Berlin public transport, but I can't "
                "reliably help with that request. Please check an "
                "appropriate official source."
            )
        return self


SCOPE_CLASSIFIER_PROMPT = """Classify the current request for a Berlin public-
transport assistant. Conversation history is context only. Structured routing
fields are supplied separately and should be used when present.

Return in_scope for Berlin/VBB local public-transport policies, fares,
accessibility, departures, and journeys whose relevant endpoints are within the
supported Berlin/VBB area.

Incomplete or ambiguous Berlin transport requests remain in_scope. Missing
stations, destinations, or passenger details should be handled by a later
clarification guard, not treated as unrelated or out of scope. Words such as
"here" and "there" are unresolved route slots, not evidence of another topic.

Return out_of_scope for unrelated topics, another region's transport rules, or
intercity journeys between Berlin and a city outside the supported area. A
journey does not become in-scope merely because one endpoint is Berlin.

Return mixed only when the user independently asks for both a supported Berlin
transport task and an unsupported task. Provide a self-contained
in_scope_request containing only the supported task.

For mixed and out_of_scope results, write a concise, friendly boundary_message.
Do not answer or speculate about the unsupported subject, and do not invent
facts, organizations, URLs, prices, or recommendations. Return only the
requested structured output."""


@dataclass(frozen=True)
class ScopeCheck:
    status: str
    in_scope_request: str | None
    out_of_scope_topics: list[str]
    boundary_message: str | None

    @property
    def applies(self) -> bool:
        return self.status != "in_scope"


class ScopeBoundaryGuard:
    """Enforce the assistant's Berlin-public-transport product boundary."""

    trigger = "scope_boundary"

    def __init__(self, classifier=None) -> None:
        self.classifier = classifier or create_chat_model(
            num_predict=128
        ).with_structured_output(ScopeDecision)

    def check(
        self,
        message: str,
        *,
        intent: str | None = None,
        origin: str | None = None,
        destination: str | None = None,
        station: str | None = None,
        travel_area: str | None = None,
        origin_status: str = "unknown",
        destination_status: str = "unknown",
        station_status: str = "unknown",
    ) -> ScopeCheck:
        route_context = (
            "\n\nSTRUCTURED ROUTING FIELDS\n"
            f"intent: {intent or 'unknown'}\n"
            f"origin: {origin or 'missing'}\n"
            f"destination: {destination or 'missing'}\n"
            f"station: {station or 'missing'}\n"
            f"travel_area: {travel_area or 'missing'}\n"
            f"origin_status: {origin_status}\n"
            f"destination_status: {destination_status}\n"
            f"station_status: {station_status}"
        )
        decision = self.classifier.invoke(
            [
                ("system", SCOPE_CLASSIFIER_PROMPT),
                ("user", f"{message}{route_context}"),
            ]
        )
        return ScopeCheck(
            status=decision.status,
            in_scope_request=decision.in_scope_request,
            out_of_scope_topics=decision.out_of_scope_topics,
            boundary_message=decision.boundary_message,
        )

    def refusal(self, check: ScopeCheck) -> str:
        return check.boundary_message or (
            "I can help with Berlin public transport, but I can't reliably "
            "help with that request."
        )

    def mixed_notice(self, check: ScopeCheck) -> str:
        return check.boundary_message or (
            "I can only verify the Berlin public-transport part of that request."
        )
