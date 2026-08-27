from langchain_core.messages import HumanMessage, SystemMessage
from src.llm import create_chat_model
from src.models import AssistantResponse, RetrievedSource
from src.retrieval import BVGRetriever
from src.router import QueryRouter
from src.tools.transit.transitous import (
    TransitousClient,
    TransitousError,
)
from src.tools.transit.transit_formatting import (
    format_departure_board,
    format_journey_plan,
)


GENERAL_SYSTEM_PROMPT = """
You are a conversational assistant primarily focused on Berlin
public transportation.

Answer naturally and concisely.
"""

NEUTRAL_RAG_SYSTEM = (
    "You are a helpful assistant for Berlin public transport. "
    "Use the provided context when answering questions about tickets, fares, "
    "travel rules, accessibility, and services. "
    "Be concise, accurate, welcoming, and friendly."
)


class BVGAssistant:

    def __init__(self) -> None:
        self.llm = create_chat_model()

        self.retriever = BVGRetriever()
        self.router = QueryRouter()

        self.transit = TransitousClient()

    def ask(self, question: str) -> AssistantResponse:
        decision = self.router.route(question)

        if decision.intent == "journey":
            return self._handle_journey(decision)

        if decision.intent == "departure":
            return self._handle_departure(decision)

        if decision.intent == "knowledge":
            return self._handle_knowledge(question)

        return self._handle_other(question)

    def _handle_knowledge(
        self,
        question: str,
    ) -> AssistantResponse:

        retrieved = self.retriever.retrieve(question)

        context_blocks = []
        sources = []

        for document, score in retrieved:

            source = document.metadata.get(
                "source",
                "unknown",
            )

            context_blocks.append(
                f"""
SOURCE: {source}

{document.page_content}
""".strip()
            )

            sources.append(
                RetrievedSource(
                    source=source,
                    score=float(score),
                    category=document.metadata.get("category"),
                )
            )

        context = "\n\n---\n\n".join(context_blocks)

        prompt = f"""
KNOWLEDGE BASE CONTEXT

{context}

USER QUESTION

{question}
""".strip()

        response = self.llm.invoke(
            [
                SystemMessage(content=NEUTRAL_RAG_SYSTEM),
                HumanMessage(content=prompt),
            ]
        )

        return AssistantResponse(
            answer=str(response.content),
            route="knowledge",
            sources=sources,
        )

    def _handle_departure(
        self,
        decision,
    ) -> AssistantResponse:

        if not decision.station:
            return AssistantResponse(
                answer=(
                    "Which station would you like "
                    "departure information for?"
                ),
                route="departure",
            )

        try:
            board = self.transit.departures(
                decision.station
            )

        except TransitousError as exc:
            return AssistantResponse(
                answer=str(exc),
                route="departure",
            )

        return AssistantResponse(
            answer=format_departure_board(board),
            route="departure",
        )

    def _handle_journey(self, decision,) -> AssistantResponse:
        if not decision.origin or not decision.destination:
            return AssistantResponse(
                answer=(
                    "Please provide an origin and destination "
                    "to plan the journey."
                ),
                route="journey",
            )

        try:
            plan = self.transit.plan_journey(
                origin=decision.origin,
                destination=decision.destination,
            )

        except TransitousError as exc:
            return AssistantResponse(
                answer=str(exc),
                route="journey",
            )

        return AssistantResponse(
            answer=format_journey_plan(plan),
            route="journey",
        )

    def _handle_other(
        self,
        question: str,
    ) -> AssistantResponse:

        response = self.llm.invoke(
            [
                SystemMessage(
                    content=GENERAL_SYSTEM_PROMPT
                ),
                HumanMessage(
                    content=question
                ),
            ]
        )

        return AssistantResponse(
            answer=str(response.content),
            route="other",
        )