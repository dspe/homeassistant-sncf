"""Read public SNCF GTFS schedules and GTFS-RT; no Home Assistant dependency."""

import csv
from datetime import UTC, datetime, timedelta
from html import escape, unescape
import io
from math import ceil
import re
from typing import Any
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2 as rt

PARIS = ZoneInfo("Europe/Paris")
ORIGIN = "87394114"
DESTINATION = "87391003"


def _station(value: str, uic: str) -> bool:
    return re.search(rf"(?<!\d){uic}(?!\d)", value) is not None


def _seconds(value: str) -> int:
    hours, minutes, seconds = map(int, value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _number(trip_id: str) -> str:
    match = re.match(r"OCESN(\d+)[A-Za-z]", trip_id)
    return match[1] if match else ""


def parse_schedule(content: bytes) -> dict[str, Any]:
    """Keep only rail trips boarding Épernon before alighting in Montparnasse."""
    with ZipFile(io.BytesIO(content)) as archive:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig"))
        routes = {r["route_id"] for r in rows("routes.txt") if r["route_type"] in {"2", "100", "106"}}
        trips = {r["trip_id"]: r for r in rows("trips.txt") if r["route_id"] in routes}
        stops = {r["stop_id"]: r for r in rows("stops.txt")}
        origin = {sid for sid, s in stops.items() if _station(sid, ORIGIN) or _station(s.get("parent_station", ""), ORIGIN)}
        dest = {sid for sid, s in stops.items() if _station(sid, DESTINATION) or _station(s.get("parent_station", ""), DESTINATION)}
        calls = {}
        for row in rows("stop_times.txt"):
            if row["trip_id"] in trips and row["stop_id"] in origin | dest:
                calls.setdefault(row["trip_id"], []).append(row)
        selected = []
        for trip_id, times in calls.items():
            trip = trips[trip_id]
            for start in times:
                if start["stop_id"] not in origin or start.get("pickup_type") == "1":
                    continue
                end = next((t for t in times if t["stop_id"] in dest
                    and int(t["stop_sequence"]) > int(start["stop_sequence"])
                    and t.get("drop_off_type") != "1"), None)
                if end is not None:
                    selected.append({
                        "trip_id": trip_id, "number": trip.get("trip_headsign") or _number(trip_id),
                        "service_id": trip["service_id"], "route_id": trip["route_id"],
                        "departure": _seconds(start["departure_time"]),
                        "arrival": _seconds(end["arrival_time"]),
                    })
        services = {t["service_id"] for t in selected}
        dates = {}
        for row in rows("calendar_dates.txt"):
            if row["service_id"] in services:
                dates.setdefault(row["date"], {})[row["service_id"]] = row["exception_type"] == "1"
        weekly = [r for r in rows("calendar.txt") if r["service_id"] in services] if "calendar.txt" in archive.namelist() else []
    if not selected:
        raise ValueError("Aucun train direct Épernon → Paris trouvé dans le GTFS")
    return {"trips": selected, "dates": dates, "weekly": weekly}


def _active(schedule, service_id, day):
    date = day.strftime("%Y%m%d")
    exceptions = schedule["dates"].get(date, {})
    if service_id in exceptions:
        return exceptions[service_id]
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[day.weekday()]
    return any(r["service_id"] == service_id and r["start_date"] <= date <= r["end_date"]
               and r[weekday] == "1" for r in schedule["weekly"])


def _service_time(day, seconds):
    # GTFS times are seconds from local noon minus 12h, including DST days.
    noon = datetime.combine(day, datetime.min.time(), PARIS).replace(hour=12)
    return datetime.fromtimestamp(noon.timestamp() - 43200 + seconds, PARIS)


def _event_time(event, scheduled):
    if event.HasField("time"):
        return datetime.fromtimestamp(event.time, PARIS)
    if event.HasField("delay"):
        return datetime.fromtimestamp(scheduled.timestamp() + event.delay, PARIS)
    return None


def _trip_matches(descriptor, trip, date):
    if descriptor.HasField("start_date") and descriptor.start_date != date:
        return False
    return descriptor.trip_id == trip["trip_id"] or bool(_number(descriptor.trip_id) and _number(descriptor.trip_id) == trip["number"])


def build_board(schedule, updates, alerts, now: datetime, count=5):
    """Return schedule rows enriched only with fresh, unambiguous GTFS-RT data."""
    now = now.astimezone(PARIS)
    instances = {}
    for offset in (-1, 0, 1):
        day = now.date() + timedelta(days=offset)
        for trip in schedule["trips"]:
            if _active(schedule, trip["service_id"], day):
                scheduled = _service_time(day, trip["departure"])
                if now.timestamp() - 10800 <= scheduled.timestamp() <= now.timestamp() + 86400:
                    instances[(trip["number"], day.strftime("%Y%m%d"), scheduled.timestamp())] = (trip, scheduled)
    # The current GTFS can already omit cancelled/added trips. Preserve RT-only
    # trips when both Épernon and Paris plus an explicit departure are supplied.
    if updates is not None:
        for entity in updates.entity:
            if not entity.HasField("trip_update"):
                continue
            update = entity.trip_update
            origin = next((i for i, s in enumerate(update.stop_time_update) if _station(s.stop_id, ORIGIN)), None)
            if origin is None or not any(_station(s.stop_id, DESTINATION) for s in update.stop_time_update[origin+1:]):
                continue
            stop = update.stop_time_update[origin]
            if not stop.departure.HasField("time") or not update.trip.start_date:
                continue
            number = _number(update.trip.trip_id)
            scheduled = datetime.fromtimestamp(stop.departure.time - stop.departure.delay, PARIS)
            if number and not any(k[0] == number and k[1] == update.trip.start_date for k in instances):
                instances[(number, update.trip.start_date, scheduled.timestamp())] = (
                    {"trip_id": update.trip.trip_id, "number": number, "route_id": update.trip.route_id}, scheduled)
    result = []
    for (number, date, _), (trip, scheduled) in instances.items():
        cancelled = warning = False
        expected = None
        messages = []
        if updates is not None:
            matches = [e.trip_update for e in updates.entity if e.HasField("trip_update")
                       and e.trip_update.trip.start_date == date and _trip_matches(e.trip_update.trip, trip, date)]
            # Do not attach one commercial number to several departures on a day.
            if sum(k[0] == number and k[1] == date for k in instances) == 1 and len(matches) == 1:
                update = matches[0]
                cancelled = update.trip.schedule_relationship == rt.TripDescriptor.CANCELED
                for stop in update.stop_time_update:
                    if _station(stop.stop_id, ORIGIN):
                        cancelled |= stop.schedule_relationship == rt.TripUpdate.StopTimeUpdate.SKIPPED
                        if stop.schedule_relationship != rt.TripUpdate.StopTimeUpdate.NO_DATA:
                            expected = _event_time(stop.departure, scheduled)
                    if _station(stop.stop_id, DESTINATION) and stop.schedule_relationship == rt.TripUpdate.StopTimeUpdate.SKIPPED:
                        warning = True
                        messages.append("Arrêt à Paris non desservi")
        if alerts is not None:
            for entity in alerts.entity:
                if not entity.HasField("alert"):
                    continue
                alert = entity.alert
                stamp = scheduled.timestamp()
                if alert.active_period and not any((not p.HasField("start") or p.start <= stamp)
                    and (not p.HasField("end") or stamp < p.end) for p in alert.active_period):
                    continue
                for selector in alert.informed_entity:
                    if selector.HasField("trip") and not _trip_matches(selector.trip, trip, date):
                        continue
                    if selector.route_id and selector.route_id != trip["route_id"]:
                        continue
                    if selector.stop_id and not (_station(selector.stop_id, ORIGIN) or _station(selector.stop_id, DESTINATION)):
                        continue
                    if not (selector.HasField("trip") or selector.route_id or selector.stop_id):
                        continue
                    warning = True
                    if alert.effect == rt.Alert.NO_SERVICE and (selector.HasField("trip") or _station(selector.stop_id, ORIGIN)):
                        cancelled = True
                    texts = alert.header_text.translation
                    if texts:
                        text = next((t.text for t in texts if t.language == "fr"), texts[0].text)
                        messages.append(unescape(re.sub(r"<[^>]+>", "", text)))
                    break
        delay = ceil((expected.timestamp() - scheduled.timestamp()) / 60) if expected else None
        status = "⚪ Horaire prévu"
        if cancelled:
            status = "🔴 Supprimé"
        elif delay is not None and delay > 0:
            status = f"🟠 +{delay} min"
        elif warning:
            status = "🟠 Perturbation"
        elif expected:
            status = "🟢 À l’heure" if delay == 0 else "🟠 En avance"
        until = scheduled if cancelled else expected or scheduled
        if not now.timestamp() <= until.timestamp() <= now.timestamp() + 86400:
            continue
        result.append({
            "numero": escape(number), "prevu": scheduled.strftime("%H:%M" if scheduled.date() == now.date() else "%d/%m %H:%M"),
            "estime": expected.strftime("%H:%M") if expected and not cancelled else "—",
            "statut": status, "tri": scheduled.timestamp(), "supprime": cancelled,
            "retard_minutes": delay if not cancelled else None,
            "depart_prevu": scheduled.isoformat(),
            "depart_estime": expected.isoformat() if expected and not cancelled else None,
            "messages": list(dict.fromkeys(messages)),
        })
    return sorted(result, key=lambda row: row["tri"])[:count]
