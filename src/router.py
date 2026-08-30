from typing import Literal
from pydantic import BaseModel, Field
from src.config import APP_SETTINGS
from src.llm import create_chat_model


class ConversationFacts(BaseModel):
    ticket_type: str | None = Field(
        default=None,
        description=(
            "Exact ticket type explicitly stated by the user, such as "
            "single ticket, 24-hour ticket, or monthly ticket."
        ),
    )
    passenger_details: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit passenger ages or counts. Convert 'three of us' to "
            "'3 passengers' and 'my 16-year-old' to 'age 16'."
        ),
    )
    travel_area: str | None = Field(
        default=None,
        description=(
            "Explicit fare zones or journey destinations, such as zones AB "
            "or BER Airport."
        ),
    )
    travel_period: str | None = Field(
        default=None,
        description=(
            "Explicit day, date, duration, or period such as today, tomorrow "
            "morning, or a day trip."
        ),
    )
    journey_pattern: str | None = Field(
        default=None,
        description=(
            "Explicit number or pattern of journeys, such as one journey, "
            "return journey, four trips, or unlimited travel."
        ),
    )
    validation_time: str | None = Field(
        default=None,
        description=(
            "Explicit time when an existing ticket was bought or validated."
        ),
    )


class RouteDecision(BaseModel):
    intent: Literal[
        "knowledge",
        "journey",
        "departure",
        "other",
    ]

    request_type: Literal[
        "child_travel",
        "ticket_recommendation",
        "ticket_validity",
        "other",
    ] = Field(
        default="other",
        description=(
            "Completeness-policy request type. This is independent from intent."
        ),
    )

    facts: ConversationFacts = Field(
        default_factory=ConversationFacts,
        description=(
            "Relevant facts extracted from the entire conversation. "
            "Use null or an empty list when a fact was not supplied."
        ),
    )

    origin: str | None = None
    destination: str | None = None
    station: str | None = None
    origin_status: Literal["resolved", "missing", "ambiguous", "unknown"] = "unknown"
    destination_status: Literal["resolved", "missing", "ambiguous", "unknown"] = "unknown"
    station_status: Literal["resolved", "missing", "ambiguous", "unknown"] = "unknown"

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

    Independently classify a completeness request_type. A policy request can
    have intent=knowledge even when it mentions a journey or destination.

    child_travel:
    - Whether a child, daughter, or son may travel on a passenger's ticket.

    ticket_recommendation:
    - The user asks you to select, recommend, or choose a ticket for them.
    - Do not use this for factual comparisons such as whether AB or ABC is
      required for a destination.

    ticket_validity:
    - Whether an existing, owned, previously purchased, or demonstratively
      referenced ticket ("this ticket", "my ticket", or "it") can be used.

    other:
    - Requests that do not match those three policy-information types.

    Extract these facts from the entire conversation when stated:
    - ticket_type
    - passenger_details, including ages or adult/child counts
    - travel_area, including zones or destinations
    - travel_period
    - journey_pattern, such as one, return, or several journeys
    - validation_time

    Never infer a fact that the user did not provide.

    Examples:

    User: Can my daughter travel with me on this ticket?
    Output fields:
    - intent=knowledge
    - request_type=child_travel
    - ticket_type=null
    - passenger_details=[]

    Conversation: Can my daughter travel on this ticket? / She is 7 and I
    have a 24-hour ticket for zones AB.
    Output fields:
    - intent=knowledge
    - request_type=child_travel
    - ticket_type=24-hour ticket
    - passenger_details=["age 7"]
    - travel_area=zones AB

    User: Which ticket should the three of us buy for today?
    Output fields:
    - intent=knowledge
    - request_type=ticket_recommendation
    - passenger_details=["3 passengers"]
    - travel_period=today

    User: Can I use this ticket to get to BER Airport?
    Output fields:
    - intent=knowledge
    - request_type=ticket_validity
    - ticket_type=null
    - travel_area=BER Airport

    User: Do I need an AB or ABC ticket to travel to BER Airport?
    Output fields:
    - intent=knowledge
    - request_type=other
    - travel_area=BER Airport

    User: How do I get from Alexanderplatz to Zoologischer Garten?
    Output fields:
    - intent=journey
    - request_type=other
    - origin=Alexanderplatz
    - destination=Zoologischer Garten

    User: I need to get to Zoologischer Garten.
    Output fields:
    - intent=journey
    - request_type=other
    - origin=null
    - destination=Zoologischer Garten

    User: What are the next departures?
    Output fields:
    - intent=departure
    - request_type=other
    - station=null

    For each route slot, also classify resolution status:
    - resolved: a specific station or place is explicitly provided or clearly
      resolved from user-authored conversation;
    - ambiguous: a vague reference such as "here", "there", "near downtown",
      "the usual station", or "that place" cannot be resolved;
    - missing: no value was provided.
    Never mark a vague reference as resolved.

    """

class QueryRouter:
    def __init__(self) -> None:
        llm = create_chat_model(
            num_predict=APP_SETTINGS.router_num_predict
        )

        self.router = llm.with_structured_output(RouteDecision)

    def route(self, message: str) -> RouteDecision:
        return self.router.invoke(
            [
                ("system", ROUTER_SYSTEM_PROMPT),
                ("user", message),
            ]
        )
