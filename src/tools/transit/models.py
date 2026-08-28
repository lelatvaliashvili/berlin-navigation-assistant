import datetime
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Departure:
    line: str
    direction: str
    departure: datetime #real-time departure time
    scheduled_departure: datetime | None #scheduled departure times, fallback for when real-time is not available
    track: str | None
    realtime: bool
    cancelled: bool


@dataclass(frozen=True)
class DepartureBoard:
    stop_name: str
    departures: list[Departure]


@dataclass(frozen=True)
class JourneySegment:
    """segment inside each journey option describing a step within a journey"""
    mode: str
    line: str | None
    origin: str
    destination: str
    departure: datetime | None
    arrival: datetime | None
    direction: str | None


@dataclass(frozen=True)
class Journey:
    """mid-level hierarchy description each journey option"""
    departure: datetime
    arrival: datetime
    duration_in_minutes: int
    transfers: int
    segment: list[JourneySegment]


@dataclass(frozen=True)
class JourneyPlan:
    """Higher level hierarchy that stores different journey options"""
    origin: str
    destination: str
    journeys: list[Journey]

