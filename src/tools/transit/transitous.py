from __future__ import annotations
from datetime import datetime
from typing import Any
import httpx
from src.config import TRANSITOUS_SETTINGS
from src.tools.transit.constants import LOCAL_TRANSIT_MODES, BERLIN_TIMEZONE
from src.tools.transit.models import JourneyPlan, DepartureBoard, Departure, Journey, JourneySegment

class TransitousError(RuntimeError):
    """Transitous could not provide a transit result."""

class TransitousClient:
    def __init__( self, base_url: str = TRANSITOUS_SETTINGS.base_url,
                  timeout_seconds: float = TRANSITOUS_SETTINGS.timeout_seconds,
                  transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.user_agent = TRANSITOUS_SETTINGS.user_agent

    def departures(self, station_name: str, departure_count: int = TRANSITOUS_SETTINGS.departures_count, ) -> DepartureBoard:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers={"User-Agent": self.user_agent},
            ) as client:
                stop = self._get_station_by_name(client, station_name)

                if stop is None:
                    raise TransitousError(
                        f" Please double check the name of the station as I was unable to find '{station_name}'. After that, try again.")

                departures_response = client.get(
                    "/api/v6/stoptimes",
                    params={
                        "stopId": stop["id"],
                        "n": departure_count,
                        "language": "en",
                        "withAlerts": "false", #disable service alerts
                    },
                )

                departures_response.raise_for_status() #hhtpx.HTTPError
                payload = departures_response.json()
        except TransitousError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise TransitousError(
                "Live departure data is temporarily unavailable. Please try again later."
            ) from exc

        return _parse_departure_board(
            payload=payload,
            fallback_stop_name=str(stop["name"]),
            departure_count=departure_count,
        )

    def plan_journey(self, origin: str, destination: str,
                     journey_result_count: int = TRANSITOUS_SETTINGS.journey_result_count,) -> JourneyPlan:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers={"User-Agent": self.user_agent},
            ) as client:
                origin_stop = self._get_station_by_name(client, origin)
                destination_stop = self._get_station_by_name(client, destination)
                if origin_stop is None:
                    raise TransitousError(
                        f"I couldn't find a Berlin transit stop matching '{origin}'."
                    )
                if destination_stop is None:
                    raise TransitousError(
                        f"I couldn't find a Berlin transit stop matching '{destination}'."
                    )

                response = client.get(
                    "/api/v6/plan",
                    params={
                        "fromPlace": origin_stop["id"],
                        "toPlace": destination_stop["id"],
                        "numItineraries": journey_result_count,
                        "maxItineraries": journey_result_count,
                        "detailedLegs": "false",
                        "language": "en",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except TransitousError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise TransitousError(
                "Journey planning is temporarily unavailable. Please try again later."
            ) from exc

        journeys = _parse_journeys(payload)
        return JourneyPlan(
            origin=str(origin_stop.get("name") or origin),
            destination=str(destination_stop.get("name") or destination),
            journeys=journeys[:journey_result_count],
        )

    def _get_station_by_name(self, client: httpx.Client, station_name:str) -> dict[str, Any] | None:
        candidates = self._fetch_stop_candidates(client, station_name)
        return _select_berlin_stop(candidates)

    def _fetch_stop_candidates(self, client: httpx.Client,  station_name: str) -> Any:
        response = client.get(
            "/api/v1/geocode",
            params={
                "text": f"{station_name} Berlin",
                "type": "STOP",
                "language": "en",
                "numResults": 5,
            },
        )
        response.raise_for_status()
        return response.json()


def _select_berlin_stop(candidates: Any) -> dict[str, Any] | None:
    if not isinstance(candidates, list):
        return None

    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("id"):
            continue

        is_supported_berlin_stop = _is_supported_berlin_stop(candidate)
        if is_supported_berlin_stop:
           return candidate #preserves Transitous' relevance order (first candidate by relevance), no need for re-sorting

    return None

def _is_supported_berlin_stop(candidate: dict[str, Any]) -> bool:
    areas = candidate.get("areas") or []
    modes = set(candidate.get("modes") or [])

    in_berlin = any(isinstance(area, dict) and area.get("name") == "Berlin" for area in areas)
    has_supported_mode = any(modes & LOCAL_TRANSIT_MODES)

    return in_berlin and has_supported_mode


def _parse_departure_board(
    payload: Any,
    fallback_stop_name: str,
    departure_count: int,
) -> DepartureBoard:

    departures = []
    for raw_departure in payload.get("stopTimes") or []:
        if not isinstance(raw_departure, dict):
            continue
        departure = _parse_departure(raw_departure)

        if departure is not None:
            departures.append(departure)

    place = payload.get("place")

    if isinstance(place, dict):
        stop_name = place.get("name")
    else:
        stop_name = fallback_stop_name

    return DepartureBoard(
        stop_name=str(stop_name),
        departures=departures[:departure_count],
    )


def _parse_departure(item: dict[str, Any]) -> Departure | None:
    place = item.get("place") or {}
    departure_value = place.get("departure") or place.get("scheduledDeparture")

    if not departure_value:
        return None

    departure = _parse_datetime(departure_value)

    if departure is None:
        return None
    scheduled = _parse_datetime(place.get("scheduledDeparture"))

    return Departure(
        line=str(item.get("displayName") or item.get("routeShortName") or item.get("mode") or "Service"),
        direction=str(item.get("headsign") or "unknown direction"),
        departure=departure,
        scheduled_departure=scheduled,
        track=place.get("track"),
        realtime=bool(item.get("realTime")),
        cancelled=bool(item.get("cancelled") or item.get("tripCancelled")),
    )


def _parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(value).astimezone(BERLIN_TIMEZONE)
    except (TypeError, ValueError):
        return None


def _parse_journeys(payload: Any) -> list[Journey]:
    if not isinstance(payload, dict):
        return []

    journeys = []

    for raw_journey in payload.get("itineraries") or []:
        journey = _parse_journey(raw_journey)
        if journey is not None:
            journeys.append(journey)

    return journeys

def _parse_journey(item: Any) -> Journey | None:
    if not isinstance(item, dict):
        return None

    departure = _parse_datetime(item.get("startTime"))
    arrival = _parse_datetime(item.get("endTime"))

    if departure is None or arrival is None:
        return None

    segments = []

    for raw_leg in item.get("legs") or []:
        if not isinstance(raw_leg, dict):
            continue

        from_place = raw_leg.get("from") or {}
        to_place = raw_leg.get("to") or {}

        segments.append(
            JourneySegment(
                mode=str(raw_leg.get("mode") or "UNKNOWN"),
                line=(
                    raw_leg.get("displayName")
                    or raw_leg.get("routeShortName")
                ),
                origin=str(
                    from_place.get("name") or "Unknown stop"
                ),
                destination=str(
                    to_place.get("name") or "Unknown stop"
                ),
                departure=_parse_datetime(
                    raw_leg.get("startTime")
                ),
                arrival=_parse_datetime(
                    raw_leg.get("endTime")
                ),
                direction=raw_leg.get("headsign"),
            )
        )

    # Prefer Transitous' own transfer count.
    raw_transfers = item.get("transfers")

    if isinstance(raw_transfers, int):
        transfers = raw_transfers
    else:
        transit_segments = [
            segment
            for segment in segments
            if segment.mode not in {"WALK", "FOOT"}
        ]

        transfers = max(
            0,
            len(transit_segments) - 1,
        )

    return Journey(
        departure=departure,
        arrival=arrival,
        duration_in_minutes=round(
            (arrival - departure).total_seconds() / 60
        ),
        transfers=transfers,
        segment=segments,
    )
