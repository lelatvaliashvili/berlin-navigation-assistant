from typing import Literal
from pydantic import BaseModel, Field
from src.llm import create_chat_model


class RouteDecision(BaseModel):
    intent: Literal[
        "knowledge",
        "journey",
        "departure",
        "other",
    ]

    origin: str | None = None
    destination: str | None = None
    station: str | None = None

    reasoning_summary: str = Field(
        description=(
            "Brief classification explanation. "
            "Do not include hidden chain-of-thought."
        )
    )


ROUTER_SYSTEM_PROMPT = """
    Classify a user's Berlin transportation request.
    
    Use:
    
    knowledge:
    - Questions about tickets, prices, fare zones, passenger rules,
      ticket validity, ticket inspections, bicycles, accessibility,
      subscriptions, or other transport policies.
    
    journey:
    - Requests asking how to travel from one place or station to another.
    - Extract origin and destination when they are available in the request.
    
    departure:
    - Requests asking for upcoming or current departures from a station.
    - Extract the station when it is available in the request.
    
    other:
    - Anything not covered above.
    """

class QueryRouter:
    def __init__(self) -> None:
        llm = create_chat_model()

        self.router = llm.with_structured_output(RouteDecision)

    def route(self, message: str) -> RouteDecision:
        return self.router.invoke(
            [
                ("system", ROUTER_SYSTEM_PROMPT),
                ("user", message),
            ]
        )