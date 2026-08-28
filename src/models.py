from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievedSource:
    source: str
    score: float
    category: str | None = None


@dataclass
class AssistantResponse:
    answer: str
    route: str
    sources: list[RetrievedSource] = field(default_factory=list)
    guardrail_triggers: list[str] = field(default_factory=list)
    guardrail_details: dict[str, object] = field(default_factory=dict)

@dataclass
class ConversationState:
    history: list = field(default_factory=list)
    pending_intent: str | None = None
    origin: str | None = None
    destination: str | None = None
    station: str | None = None
