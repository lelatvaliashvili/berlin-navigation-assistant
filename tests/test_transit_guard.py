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
