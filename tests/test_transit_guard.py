from src.guardrails.transit import TransitPreconditionGuard


def test_journey_requires_both_endpoints() -> None:
    guard = TransitPreconditionGuard()
    result = guard.check(
        intent="journey",
        origin="Alexanderplatz",
        destination=None,
    )

    assert result.missing_fields == ["destination"]
    assert not result.complete


def test_departure_requires_station() -> None:
    guard = TransitPreconditionGuard()
    result = guard.check(intent="departure", station=None)

    assert result.missing_fields == ["station"]


def test_complete_journey_passes() -> None:
    guard = TransitPreconditionGuard()
    result = guard.check(
        intent="journey",
        origin="Alexanderplatz",
        destination="Zoologischer Garten",
    )

    assert result.complete


def test_unresolved_route_references_require_clarification() -> None:
    guard = TransitPreconditionGuard()

    departure = guard.check(intent="departure", station="here")
    journey = guard.check(
        intent="journey",
        origin="Alexanderplatz",
        destination="there",
    )

    assert departure.missing_fields == ["station"]
    assert journey.missing_fields == ["destination"]


def test_ambiguous_structured_slot_requires_clarification() -> None:
    guard = TransitPreconditionGuard()

    result = guard.check(
        intent="journey",
        origin="Alexanderplatz",
        destination="somewhere downtown",
        origin_status="resolved",
        destination_status="ambiguous",
    )

    assert result.missing_fields == ["destination"]
