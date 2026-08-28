from dataclasses import dataclass


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
    ) -> TransitPreconditionResult:
        if intent == "departure":
            missing = [] if station else ["station"]
            return TransitPreconditionResult(True, missing)

        if intent == "journey":
            missing = [
                field
                for field, value in (
                    ("origin", origin),
                    ("destination", destination),
                )
                if not value
            ]
            return TransitPreconditionResult(True, missing)

        return TransitPreconditionResult(False, [])

    def clarification(self, result: TransitPreconditionResult) -> str:
        return " ".join(self.prompts[field] for field in result.missing_fields)
