"""Combine SNCF schedules and explicitly linked disruptions, without HA state."""

from datetime import datetime, timedelta
from html import escape
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=PARIS)
    except (ValueError, TypeError):
        return None


def _key(departure: dict[str, Any]) -> tuple[str, str]:
    info = departure.get("display_informations") or {}
    times = departure.get("stop_date_time") or {}
    number = info.get("headsign") or info.get("trip_short_name") or "—"
    base = times.get("base_departure_date_time") or times.get("departure_date_time", "")
    return str(number), base


def _pattern_applies(pattern: dict[str, Any], when: datetime) -> bool:
    dates = pattern.get("application_period") or {}
    week = pattern.get("week_pattern") or {}
    for day in (when, when - timedelta(days=1)):
        if not dates.get("begin", "z") <= day.strftime("%Y%m%d") <= dates.get("end", ""):
            continue
        if week and not week.get(WEEKDAYS[day.weekday()], False):
            continue
        slots = pattern.get("time_slots") or []
        if not slots and day == when:
            return True
        for slot in slots:
            start, end = slot.get("begin", "z"), slot.get("end", "")
            time = when.strftime("%H%M%S")
            if start < end and day == when and start <= time < end:
                return True
            if start > end and (
                (day == when and time >= start) or (day != when and time < end)
            ):
                return True
    return False


def _applies(impact: dict[str, Any], when: datetime) -> bool:
    periods = impact.get("application_periods") or []
    value = when.strftime("%Y%m%dT%H%M%S")
    active = any(p.get("begin", "z") <= value <= p.get("end", "") for p in periods)
    patterns = impact.get("application_patterns") or []
    if patterns:
        return (active or not periods) and any(_pattern_applies(p, when) for p in patterns)
    return active


def build_departures(
    planned: dict[str, Any], live: dict[str, Any], now: datetime, count: int = 5
) -> list[dict[str, Any]]:
    """Retain cancelled trains and never infer cancellation from absence."""
    now = now.astimezone(PARIS)
    groups: dict[tuple[str, str], list[tuple[dict[str, Any], bool]]] = {}
    for payload, is_live in ((live, True), (planned, False)):
        for departure in payload.get("departures", []):
            groups.setdefault(_key(departure), []).append((departure, is_live))
    impacts: dict[str, dict[str, Any]] = {}
    # Prefer the realtime copy when both responses contain the same disruption.
    for payload in (live, planned):
        for impact in payload.get("disruptions") or []:
            if impact.get("id"):
                impacts.setdefault(impact["id"], impact)
    rows = []
    for (number, base), versions in groups.items():
        departure, is_live = versions[0]
        info = departure.get("display_informations") or {}
        direction = (info.get("direction") or "").lower()
        mode = (info.get("physical_mode") or "").lower()
        if "paris" not in direction or "montparnasse" not in direction or "train" not in mode:
            continue
        times = departure.get("stop_date_time") or {}
        expected = times.get("departure_date_time", "")
        scheduled, estimated = _date(base), _date(expected)
        if scheduled is None or estimated is None:
            continue
        alert_ids = set()
        for other, _ in versions:
            links = (
                (other.get("display_informations") or {}).get("links", [])
                + (other.get("stop_date_time") or {}).get("links", [])
                + other.get("links", [])
            )
            alert_ids.update(link.get("id") for link in links if link.get("type") == "disruption")
        cancelled, warning = False, False
        for alert_id in alert_ids:
            impact = impacts.get(alert_id)
            if impact is None or not _applies(impact, scheduled):
                continue
            effect = (impact.get("severity") or {}).get("effect", "")
            cancelled |= effect == "NO_SERVICE"
            warning |= effect in {
                "REDUCED_SERVICE", "MODIFIED_SERVICE", "DETOUR",
                "SIGNIFICANT_DELAYS", "OTHER_EFFECT",
            }
            origin = (departure.get("stop_point") or {}).get("id")
            for obj in impact.get("impacted_objects") or []:
                for stop in obj.get("impacted_stops") or []:
                    if origin and (stop.get("stop_point") or {}).get("id") == origin:
                        cancelled |= stop.get("departure_status") == "deleted"
        delay = ceil((estimated.timestamp() - scheduled.timestamp()) / 60)
        realtime = is_live and times.get(
            "data_freshness", times.get("stop_date_time")
        ) == "realtime"
        status, estimated_label, keep_until = "⚪ Horaire prévu", "—", scheduled
        if cancelled:
            status = "🔴 Supprimé"
        elif is_live and delay > 0:
            status = f"🟠 +{delay} min"
            estimated_label, keep_until = estimated.strftime("%H:%M"), estimated
        elif warning:
            status = "🟠 Perturbation"
            # A known delay or early departure still controls when this row expires.
            if realtime:
                estimated_label, keep_until = estimated.strftime("%H:%M"), estimated
        elif realtime:
            status = "🟢 À l’heure" if delay == 0 else "🟠 En avance"
            estimated_label, keep_until = estimated.strftime("%H:%M"), estimated
        if keep_until.timestamp() < now.timestamp():
            continue
        label = scheduled.strftime("%H:%M" if scheduled.date() == now.date() else "%d/%m %H:%M")
        rows.append({
            "numero": escape(number), "prevu": label, "estime": estimated_label,
            "statut": status, "tri": base, "depart_prevu": base,
            "depart_estime": expected,
            "retard_minutes": delay if is_live and not cancelled else None,
            "supprime": cancelled,
        })
    return sorted(rows, key=lambda row: row["tri"])[:count]
