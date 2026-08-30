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
        enable_groundedness_guard: bool = False,
        enable_transit_guard: bool = False,
        enable_scope_guard: bool = False,
    ) -> None:
        self.llm = create_chat_model()
        self.retriever = BVGRetriever()
        self.router = QueryRouter()
        self.transit = TransitousClient()
        self.state = ConversationState()
        self.injection_guard = None
        self.completeness_guard = None
        self.groundedness_guard = None
        self.transit_guard = None
        self.scope_guard = None
        self.last_decision = None

        if guarded:
            enable_injection_guard = True
            enable_completeness_guard = True
            enable_groundedness_guard = True
            enable_transit_guard = True
            enable_scope_guard = True

        if enable_injection_guard:
            from src.guardrails import PromptInjectionGuard
            self.injection_guard = PromptInjectionGuard()

        if enable_completeness_guard:
            from src.guardrails import InformationCompletenessGuard
            self.completeness_guard = InformationCompletenessGuard()

        if enable_groundedness_guard:
            from src.guardrails import GroundednessGuard
            self.groundedness_guard = GroundednessGuard()

        if enable_transit_guard:
            from src.guardrails import TransitPreconditionGuard
            self.transit_guard = TransitPreconditionGuard()

        if enable_scope_guard:
            from src.guardrails import ScopeBoundaryGuard
            self.scope_guard = ScopeBoundaryGuard()

    def classify(self, question: str) -> RouteDecision:
        return self.router.route(self._router_question_with_context(question))

    def _router_question_with_context(self, question: str) -> str:
        """Give routing/extraction only user-authored facts, never AI claims."""
        if not self.state.history:
            return question
        user_messages = [
            message.content
            for message in self._recent_history()
            if isinstance(message, HumanMessage)
        ]
        if not user_messages:
            return question
        transcript = "\n".join(user_messages)
        return (
            "User conversation so far:\n"
            f"{transcript}\n\n"
            "Current user message:\n"
            f"{question}"
        )

    def ask(self, question: str,
        *,
        decision: RouteDecision | None = None,
    ) -> AssistantResponse:
        original_question = question

        if self.injection_guard is not None:
            injection = self.injection_guard.check(question)

            if injection.blocked:
                return AssistantResponse(
                    answer=self.injection_guard.refusal,
                    route="knowledge",
                    guardrail_triggers=["prompt_injection_authority"],
                    guardrail_details={
                        "reason": injection.reason,
                        "attack_type": injection.attack_type,
                    },
                )

        decision = decision or self.classify(original_question)
        self.last_decision = decision
        self._mark_unresolved_route_slots(decision, original_question)

        scope_check = None
        scope_guard = getattr(self, "scope_guard", None)
        if scope_guard is not None:
            scope_check = scope_guard.check(
                self._question_with_context(original_question),
                intent=decision.intent,
                origin=decision.origin,
                destination=decision.destination,
                station=decision.station,
                travel_area=decision.facts.travel_area,
                origin_status=decision.origin_status,
                destination_status=decision.destination_status,
                station_status=decision.station_status,
            )
            if scope_check.status == "out_of_scope":
                response = AssistantResponse(
                    answer=scope_guard.refusal(scope_check),
                    route="other",
                    guardrail_triggers=[scope_guard.trigger],
                    guardrail_details={
                        "scope": scope_check.status,
                        "out_of_scope_topics": scope_check.out_of_scope_topics,
                    },
                )
                self._remember(original_question, response.answer)
                return response
            if scope_check.status == "mixed" and scope_check.in_scope_request:
                question = scope_check.in_scope_request
                decision = self.classify(question)
                self.last_decision = decision

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

        transit_guard = getattr(self, "transit_guard", None)
        if transit_guard is not None:
            transit_check = transit_guard.check(
                intent=decision.intent,
                origin=decision.origin,
                destination=decision.destination,
                station=decision.station,
            )
            if transit_check.applies and not transit_check.complete:
                response = AssistantResponse(
                    answer=transit_guard.clarification(transit_check),
                    route=decision.intent,
                    guardrail_triggers=["transit_preconditions"],
                    guardrail_details={
                        "missing_fields": transit_check.missing_fields,
                    },
                )
                self._remember(question, response.answer)
                return response

        if decision.intent == "journey":
            response = self._handle_journey(decision)

        elif decision.intent == "departure":
            response = self._handle_departure(decision)

        elif decision.intent == "knowledge":
            response = self._handle_knowledge(question)

        else:
            response = self._handle_other(question)

        if scope_check is not None and scope_check.status == "mixed":
            response.answer = (
                f"{response.answer.rstrip()}\n\n"
                f"{scope_guard.mixed_notice(scope_check)}"
            )
            response.guardrail_triggers.append(scope_guard.trigger)
            response.guardrail_details[scope_guard.trigger] = {
                "scope": scope_check.status,
                "in_scope_request": scope_check.in_scope_request,
                "out_of_scope_topics": scope_check.out_of_scope_topics,
            }

        self._remember(original_question, response.answer)
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
    def _mark_unresolved_route_slots(decision, question: str) -> None:
        normalized = " ".join(question.casefold().split())
        unresolved = r"(?:here|there|this station|that station|this place|that place)"
        if decision.intent == "departure" and re.search(
            rf"\bfrom\s+{unresolved}\b", normalized
        ):
            decision.station_status = "ambiguous"
        if decision.intent == "journey":
            if re.search(rf"\bfrom\s+{unresolved}\b", normalized):
                decision.origin_status = "ambiguous"
            if re.search(rf"\bto\s+{unresolved}\b", normalized):
                decision.destination_status = "ambiguous"

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

        answer = str(response.content)
        triggers = []
        details = {}

        if self.groundedness_guard is not None:
            groundedness = self.groundedness_guard.check(
                question=question,
                evidence=context,
                answer=answer,
            )
            details = {
                "supported": groundedness.supported,
                "unsupported_claims": groundedness.unsupported_claims,
                "reason": groundedness.reason,
            }
            if not groundedness.supported:
                triggers.append("groundedness")
                original_answer = answer
                answer = self.groundedness_guard.repair(
                    question=question,
                    official_context=context,
                    answer=original_answer,
                    unsupported_claims=groundedness.unsupported_claims,
                )
                repair_check = self.groundedness_guard.check(
                    question=question,
                    evidence=context,
                    answer=answer,
                )
                details["original_answer"] = original_answer
                details["repair_verified"] = repair_check.supported
                if not repair_check.supported:
                    answer = self.groundedness_guard.fallback
                    details["repair_failure_reason"] = repair_check.reason

        return AssistantResponse(
            answer=answer,
            route="knowledge",
            sources=sources,
            guardrail_triggers=triggers,
            guardrail_details=details,
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
