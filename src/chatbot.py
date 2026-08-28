import re
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from src.config import (
    APP_SETTINGS,
    ASSISTANT_SYSTEM_PROMPT,
    DEPARTURE_STATION_PROMPT,
    JOURNEY_ENDPOINTS_PROMPT,
)
from src.llm import create_chat_model
from src.models import AssistantResponse, RetrievedSource, ConversationState
from src.retrieval import BVGRetriever
from src.router import QueryRouter, RouteDecision
from src.tools.transit.transitous import (
    TransitousClient,
    TransitousError,
)
from src.tools.transit.transit_formatting import (
    format_departure_board,
    format_journey_plan,
)

class BVGAssistant:

    def __init__(
        self,
        guarded: bool = False,
        enable_injection_guard: bool = False,
        enable_completeness_guard: bool = False,
    ) -> None:
        self.llm = create_chat_model()
        self.retriever = BVGRetriever()
        self.router = QueryRouter()
        self.transit = TransitousClient()
        self.state = ConversationState()
        self.injection_guard = None
        self.completeness_guard = None

        if guarded:
            enable_injection_guard = True
            enable_completeness_guard = True

        if enable_injection_guard:
            from src.guardrails import PromptInjectionGuard
            self.injection_guard = PromptInjectionGuard()

        if enable_completeness_guard:
            from src.guardrails import InformationCompletenessGuard
            self.completeness_guard = InformationCompletenessGuard()

    def classify(self, question: str) -> RouteDecision:
        return self.router.route(self._question_with_context(question)) #based on context

    def ask(self, question: str,
        *,
        decision: RouteDecision | None = None,
    ) -> AssistantResponse:
        if self.injection_guard is not None:
            injection = self.injection_guard.check(question)
            if injection.blocked:
                return AssistantResponse(
                    answer=self.injection_guard.refusal,
                    route="knowledge",
                    guardrail_triggers=["prompt_injection_authority"],
                )

        decision = decision or self.classify(question)

        if self.completeness_guard is not None:
            requirements = self.completeness_guard.evaluate(
                decision.request_type,
                decision.facts,
            )
            if requirements.applies:
                if requirements.missing_fields:
                    response = AssistantResponse(
                        answer=self.completeness_guard.clarification(
                            requirements
                        ),
                        route="knowledge",
                        guardrail_triggers=["information_completeness"],
                        guardrail_details={
                            "request_type": requirements.request_type,
                            "missing_fields": requirements.missing_fields,
                        },
                    )
                    self._remember(question, response.answer)
                    return response

        self._resolve_slots(decision, question)

        if decision.intent == "journey":
            response = self._handle_journey(decision)

        elif decision.intent == "departure":
            response = self._handle_departure(decision)

        elif decision.intent == "knowledge":
            response = self._handle_knowledge(question)

        else:
            response = self._handle_other(question)

        self._remember(question, response.answer)
        return response

    def _remember(self, question: str, answer: str) -> None:
        self.state.history.extend(
            [
                HumanMessage(content=question),
                AIMessage(content=answer),
            ]
        )

    def _resolve_slots(self, decision, question: str) -> None:
        short_follow_up = len(question.split()) <= 8
        if self.state.pending_intent and short_follow_up:
            decision.intent = self.state.pending_intent

        if decision.intent == "departure":
            if decision.station:
                self.state.station = decision.station
            elif self.state.pending_intent == "departure":
                decision.station = question.strip()
                self.state.station = decision.station

            self.state.pending_intent = (
                None if decision.station else "departure"
            )
            return

        if decision.intent == "journey":
            origin, destination = self._journey_slots(question)

            decision.origin = decision.origin or origin
            decision.destination = decision.destination or destination

            if self.state.pending_intent == "journey":
                decision.origin = decision.origin or self.state.origin
                decision.destination = (
                    decision.destination or self.state.destination
                )

                if self.state.origin and not decision.destination:
                    decision.destination = question.strip()
                elif self.state.destination and not decision.origin:
                    decision.origin = question.strip()

            if decision.origin:
                self.state.origin = decision.origin
            if decision.destination:
                self.state.destination = decision.destination

            self.state.pending_intent = (
                None
                if decision.origin and decision.destination
                else "journey"
            )
            return

        self._clear_pending_route()

    @staticmethod
    def _journey_slots(question: str) -> tuple[str | None, str | None]:
        normalized = " ".join(question.strip().split())

        from_to = re.search(
            r"\bfrom\s+(.+?)\s+to\s+(.+?)[?.!]*$",
            normalized,
            flags=re.IGNORECASE,
        )
        if from_to:
            return from_to.group(1), from_to.group(2)

        repeated_from = re.search(
            r"\bget\s+from\s+(.+?)\s+from\s+(.+?)[?.!]*$",
            normalized,
            flags=re.IGNORECASE,
        )
        if repeated_from:
            return repeated_from.group(2), repeated_from.group(1)

        to_from = re.search(
            r"\bto\s+(?!get\b|go\b|travel\b)"
            r"(.+?)\s+from\s+(.+?)[?.!]*$",
            normalized,
            flags=re.IGNORECASE,
        )
        if to_from:
            return to_from.group(2), to_from.group(1)

        destination_only = re.fullmatch(
            r"to\s+(.+?)[?.!]*",
            normalized,
            flags=re.IGNORECASE,
        )
        if destination_only:
            return None, destination_only.group(1)

        return None, None

    def _clear_pending_route(self) -> None:
        self.state.pending_intent = None
        self.state.origin = None
        self.state.destination = None
        self.state.station = None

    def reset_session(self) -> None:
        self.state = ConversationState()

    def _question_with_context(self, question: str) -> str:
        if not self.state.history:
            return question

        transcript = "\n".join(
            f"{message.type}: {message.content}"
            for message in self._recent_history()
        )
        return (
            "Conversation so far:\n"
            f"{transcript}\n\n"
            "Current user message:\n"
            f"{question}"
        )

    def _recent_history(self) -> list:
        return self.state.history[
            -APP_SETTINGS.history_message_limit:
        ]

    def _handle_knowledge(
        self,
        question: str,
    ) -> AssistantResponse:

        retrieval_query = self._question_with_context(question)
        retrieved = self.retriever.retrieve(retrieval_query)

        context_blocks = []
        sources = []

        for document, score in retrieved:

            source = document.metadata.get(
                "source",
                "unknown",
            )

            context_blocks.append(
                f"SOURCE: {source}\n\n"
                f"{document.page_content}"
            )

            sources.append(
                RetrievedSource(
                    source=source,
                    score=float(score),
                    category=document.metadata.get("category"),
                )
            )

        context = "\n\n---\n\n".join(context_blocks)

        prompt = (
            "KNOWLEDGE BASE CONTEXT\n\n"
            f"{context}\n\n"
            "USER QUESTION\n\n"
            f"{question}"
        )

        response = self.llm.invoke(
            [
                SystemMessage(content=ASSISTANT_SYSTEM_PROMPT),
                *self._recent_history(),
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
                answer=DEPARTURE_STATION_PROMPT,
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
                answer=JOURNEY_ENDPOINTS_PROMPT,
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

        return AssistantResponse(answer=format_journey_plan(plan), route="journey")

    def _handle_other(
        self,
        question: str,
    ) -> AssistantResponse:

        response = self.llm.invoke(
            [
                SystemMessage(content=ASSISTANT_SYSTEM_PROMPT),
                *self._recent_history(),
                HumanMessage(content=question),
            ]
        )

        return AssistantResponse(answer=str(response.content), route="other")
