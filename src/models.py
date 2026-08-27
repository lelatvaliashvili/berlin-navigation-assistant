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