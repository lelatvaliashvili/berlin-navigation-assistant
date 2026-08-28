from src.tools.transit.models import DepartureBoard, JourneyPlan


def format_departure_board(board: DepartureBoard, provenance_notice: str | None = None,) -> str:
    """ API facts directly rather than asking the LLM to restate them."""
    if not board.departures:
        answer = f"I found {board.stop_name}, but no upcoming departures are listed."
        return f"{answer}\n{provenance_notice}" if provenance_notice else answer

    lines = [f"Next departures from {board.stop_name} (via Transitous):"]
    if provenance_notice:
        lines.append(provenance_notice)
    for departure in board.departures:
        status = "cancelled" if departure.cancelled else "realtime" if departure.realtime else "scheduled"
        detail = (
            f"{departure.departure:%H:%M} — {departure.line} toward "
            f"{departure.direction}"
        )
        if departure.track:
            detail += f", track {departure.track}"
        if departure.scheduled_departure and departure.departure > departure.scheduled_departure:
            delay_minutes = round(
                (departure.departure - departure.scheduled_departure).total_seconds() / 60
            )
            detail += f", {delay_minutes} min late"
        lines.append(f"- {detail} ({status})")
    lines.append("Times can change; check station displays before travelling.")
    return "\n".join(lines)


def format_journey_plan(plan: JourneyPlan) -> str:
    """Render structured journey results without allowing the LLM to add claims."""
    if not plan.journeys:
        return f"I found {plan.origin} and {plan.destination}, but no journeys are currently listed."

    lines = [f"Journey options from {plan.origin} to {plan.destination} (via Transitous):"]

    for index, journey in enumerate(plan.journeys, start=1):
        if journey.transfers == 0:
            transfer_label = "direct"
        elif journey.transfers == 1:
            transfer_label = "1 transfer"
        else:
            transfer_label = f"{journey.transfers} transfers"

        lines.append(
            f"{index}. {journey.departure:%H:%M}–{journey.arrival:%H:%M} "
            f"({journey.duration_in_minutes} min, {transfer_label})"
        )

        for leg in journey.segment:
            if leg.mode in {"WALK", "FOOT"}:
                if leg.origin == leg.destination:
                    lines.append(f"   - Transfer at {leg.origin}")
                else:
                    lines.append(f"   - Walk from {leg.origin} to {leg.destination}")
                continue
            service = leg.line or leg.mode.title()
            direction = f" toward {leg.direction}" if leg.direction else ""
            time = f" at {leg.departure:%H:%M}" if leg.departure else ""
            lines.append(
                f"   - Take {service}{direction} from {leg.origin} "
                f"to {leg.destination}{time}"
            )

    lines.append("Journey times can change; check station displays before travelling.")
    return "\n".join(lines)
