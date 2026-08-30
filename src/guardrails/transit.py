from dataclasses import dataclass


UNRESOLVED_REFERENCES = {
    "here",
    "there",
    "this station",
    "that station",
    "this place",
    "that place",
}


def _is_resolved(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    normalized = " ".join(value.casefold().strip().split())
    return normalized not in UNRESOLVED_REFERENCES


@dataclass(frozen=True)
class TransitPreconditionResult:
    applies: bool
    missing_fields: list[str]

    @property
    def complete(self) -> bool:
        return not self.missing_fields


class TransitPreconditionGuard:
    prompts = {
        "station": "Which station would you like departure information for?",
        "origin": "Where will your journey start?",
        "destination": "Where would you like to travel to?",
    }

    def check(
        self,
        *,
        intent: str,
        origin: str | None = None,
        destination: str | None = None,
        station: str | None = None,
        origin_status: str = "unknown",
        destination_status: str = "unknown",
        station_status: str = "unknown",
    ) -> TransitPreconditionResult:
        if intent == "departure":
            missing = [] if (
                station_status == "resolved"
                or (station_status == "unknown" and _is_resolved(station))
            ) else ["station"]
            return TransitPreconditionResult(True, missing)

        if intent == "journey":
            missing = [
                field
                for field, value, status in (
                    ("origin", origin, origin_status),
                    ("destination", destination, destination_status),
                )
                if status != "resolved"
                and not (status == "unknown" and _is_resolved(value))
            ]
            return TransitPreconditionResult(True, missing)

        return TransitPreconditionResult(False, [])

    def clarification(self, result: TransitPreconditionResult) -> str:
        return " ".join(self.prompts[field] for field in result.missing_fields)
