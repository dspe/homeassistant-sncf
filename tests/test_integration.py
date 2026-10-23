"""Public GTFS parsing, live matching, cache and actual Home Assistant flows."""

from datetime import UTC, datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile

from google.transit import gtfs_realtime_pb2 as rt
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sncf_epernon import async_migrate_entry, async_setup_entry, async_unload_entry
from custom_components.sncf_epernon.const import DOMAIN, SCHEDULE_URL, UPDATES_URL, ALERTS_URL
from custom_components.sncf_epernon.config_flow import SncfOptionsFlow
from custom_components.sncf_epernon.coordinator import SncfCoordinator
from custom_components.sncf_epernon.gtfs import PARIS, parse_schedule, build_board, _service_time
from custom_components.sncf_epernon.open_data import OpenDataClient, OpenDataError
from custom_components.sncf_epernon.sensor import SncfDeparturesSensor

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 23, 14, 0, tzinfo=PARIS)


def schedule(numbers=("862430",), departure=16*3600):
    return {"trips": [{"trip_id": f"OCESN{n}Flong_static_id", "number": n, "route_id": "rail", "service_id": "s", "departure": departure+i*600, "arrival": departure+3000+i*600} for i,n in enumerate(numbers)], "dates": {"20261023": {"s": True}, "20261024": {"s": True}}, "weekly": []}


def feed(now=NOW):
    f = rt.FeedMessage()
    f.header.gtfs_realtime_version = "2.0"
    f.header.timestamp = int(now.timestamp())
    return f


def update(f, number="862430", delay=None, cancelled=False, date="20261023", departure=16*3600):
    entity = f.entity.add(id=number)
    u = entity.trip_update
    u.trip.trip_id = f"OCESN{number}F"
    u.trip.start_date = date
    if cancelled:
        u.trip.schedule_relationship = rt.TripDescriptor.CANCELED
    stop = u.stop_time_update.add(stop_id="StopArea:OCE87394114")
    if delay is not None:
        day = datetime.strptime(date, "%Y%m%d").date()
        stop.departure.time = int(_service_time(day, departure).timestamp()) + delay
        stop.departure.delay = delay
    u.stop_time_update.add(stop_id="StopArea:OCE87391003")
    return u


def alert(f, number="862430", effect=None, start=None, end=None):
    a = f.entity.add(id="alert").alert
    a.informed_entity.add().trip.trip_id = f"OCESN{number}F"
    if effect is not None:
        a.effect = effect
    if start is not None or end is not None:
        p = a.active_period.add()
        if start is not None:
            p.start = start
        if end is not None:
            p.end = end
    a.header_text.translation.add(text="Information SNCF", language="fr")
    return a


def zip_schedule():
    content = io.BytesIO()
    with ZipFile(content, "w") as z:
        z.writestr("routes.txt", "route_id,route_type\nrail,2\nbus,3\n")
        z.writestr("stops.txt", "stop_id,parent_station\nStopPoint:OCETrain TER-87394114,StopArea:OCE87394114\nStopPoint:OCETrain TER-87391003,StopArea:OCE87391003\n")
        z.writestr("trips.txt", "route_id,service_id,trip_id,trip_headsign\nrail,s,good,862430\nbus,s,bus,426001\nrail,s,reverse,862431\nrail,s,noboard,862432\n")
        text = "trip_id,stop_id,stop_sequence,arrival_time,departure_time,pickup_type,drop_off_type\n"
        for trip, stations, pickup in (("good", ("87394114", "87391003"), 0), ("bus", ("87394114", "87391003"), 0), ("reverse", ("87391003", "87394114"), 0), ("noboard", ("87394114", "87391003"), 1)):
            for sequence, uic in enumerate(stations):
                text += f"{trip},StopPoint:OCETrain TER-{uic},{sequence+1},16:00:00,16:00:00,{pickup},0\n"
        z.writestr("stop_times.txt", text)
        z.writestr("calendar_dates.txt", "service_id,date,exception_type\ns,20261023,1\ns,20261024,2\n")
    return content.getvalue()


def snapshot():
    return {"schedule": schedule(), "updates": None, "alerts": None, "fetched_at": NOW, "warnings": [], "schedule_updated_at": NOW.isoformat(), "realtime_updated_at": None}


class GtfsTests(unittest.TestCase):
    def test_parse_only_boardable_direct_rail(self):
        parsed = parse_schedule(zip_schedule())
        self.assertEqual([t["trip_id"] for t in parsed["trips"]], ["good"])
        self.assertTrue(parsed["dates"]["20261023"]["s"])
        self.assertFalse(parsed["dates"]["20261024"]["s"])

    def test_no_realtime_is_never_green_or_cancelled(self):
        row = build_board(schedule(), None, None, NOW)[0]
        self.assertEqual(row["statut"], "⚪ Horaire prévu")
        self.assertFalse(row["supprime"])

    def test_scheduled_trains_remain_when_rt_feed_empty(self):
        self.assertEqual(build_board(schedule(), feed(), feed(), NOW)[0]["statut"], "⚪ Horaire prévu")

    def test_short_rt_ids_and_area_ids_match_long_static_point_ids(self):
        f = feed(); update(f, delay=0)
        row = build_board(schedule(), f, None, NOW)[0]
        self.assertEqual(row["statut"], "🟢 À l’heure")
        self.assertEqual(row["estime"], "16:00")

    def test_delay_after_planned_departure(self):
        f = feed(); update(f, delay=1200, departure=13*3600+50*60)
        row = build_board(schedule(departure=13*3600+50*60), f, None, NOW)[0]
        self.assertEqual(row["retard_minutes"], 20)
        self.assertEqual(row["estime"], "14:10")

    def test_explicit_cancellation(self):
        f = feed(); update(f, cancelled=True)
        row = build_board(schedule(), f, None, NOW)[0]
        self.assertTrue(row["supprime"])
        self.assertIsNone(row["retard_minutes"])

    def test_cancelled_train_omitted_from_current_gtfs_recovered(self):
        f = feed(); update(f, cancelled=True, delay=0)
        empty = {"trips": [], "dates": {}, "weekly": []}
        row = build_board(empty, f, None, NOW)[0]
        self.assertTrue(row["supprime"])
        self.assertEqual(row["numero"], "862430")

    def test_rt_only_reverse_train_not_added(self):
        f = feed(); u = update(f, delay=0)
        u.stop_time_update.reverse()
        self.assertEqual(build_board({"trips": [], "dates": {}, "weekly": []}, f, None, NOW), [])

    def test_skip_origin_cancels_skip_destination_warns(self):
        for index, cancelled in ((0, True), (1, False)):
            f = feed(); u = update(f, delay=0)
            u.stop_time_update[index].schedule_relationship = rt.TripUpdate.StopTimeUpdate.SKIPPED
            row = build_board(schedule(), f, None, NOW)[0]
            self.assertEqual(row["supprime"], cancelled)
            self.assertNotEqual(row["statut"], "🟢 À l’heure")

    def test_no_data_does_not_claim_on_time(self):
        f = feed(); u = update(f, delay=0)
        u.stop_time_update[0].schedule_relationship = rt.TripUpdate.StopTimeUpdate.NO_DATA
        self.assertEqual(build_board(schedule(), f, None, NOW)[0]["statut"], "⚪ Horaire prévu")

    def test_wrong_service_date_not_applied(self):
        f = feed(); update(f, cancelled=True, date="20261022")
        self.assertFalse(build_board(schedule(), f, None, NOW)[0]["supprime"])

    def test_ambiguous_commercial_number_not_applied(self):
        s = schedule(("862430", "862430")); f = feed(); update(f, delay=600)
        self.assertEqual(build_board(s, f, None, NOW)[0]["statut"], "⚪ Horaire prévu")

    def test_alert_no_service_and_active_period(self):
        a = feed(); alert(a, effect=rt.Alert.NO_SERVICE, start=int(NOW.timestamp()), end=int(NOW.timestamp())+86400)
        self.assertTrue(build_board(schedule(), None, a, NOW)[0]["supprime"])
        a.entity[0].alert.active_period[0].end = int(NOW.timestamp())
        self.assertFalse(build_board(schedule(), None, a, NOW)[0]["supprime"])

    def test_information_alert_is_not_cancellation(self):
        a = feed(); alert(a)
        row = build_board(schedule(), None, a, NOW)[0]
        self.assertEqual(row["statut"], "🟠 Perturbation")
        self.assertEqual(row["messages"], ["Information SNCF"])

    def test_selector_qualifiers_are_conjunctive(self):
        a = feed(); x = alert(a, effect=rt.Alert.NO_SERVICE)
        x.informed_entity[0].route_id = "wrong"
        self.assertFalse(build_board(schedule(), None, a, NOW)[0]["supprime"])
        x.informed_entity[0].ClearField("route_id")
        x.informed_entity[0].trip.start_date = "20261024"
        self.assertFalse(build_board(schedule(), None, a, NOW)[0]["supprime"])

    def test_calendar_tomorrow_count_and_expired(self):
        s = schedule(tuple(str(n) for n in range(10)))
        self.assertEqual(len(build_board(s, None, None, NOW, 7)), 7)
        rows = build_board(s, None, None, NOW.replace(hour=23), 1)
        self.assertTrue(rows[0]["prevu"].startswith("24/10"))
        s["dates"]["20261024"]["s"] = False
        self.assertEqual(build_board(s, None, None, NOW.replace(hour=23)), [])

    def test_after_midnight_gtfs_time(self):
        s = schedule(departure=24*3600+10*60)
        now = datetime(2026,10,24,0,5,tzinfo=PARIS)
        self.assertEqual(build_board(s, None, None, now)[0]["prevu"], "00:10")

    def test_five_next_trains_beyond_tomorrow(self):
        s = schedule()
        s["dates"] = {(NOW.date()+timedelta(days=day)).strftime("%Y%m%d"): {"s": True}
                      for day in (2, 3, 4, 5, 6, 8)}
        rows = build_board(s, None, None, NOW)
        self.assertEqual(len(rows), 5)
        self.assertEqual([r["depart_prevu"][:10] for r in rows],
                         ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"])
        self.assertTrue(all(r["statut"] == "⚪ Horaire prévu" for r in rows))
        self.assertEqual(len(build_board(s, None, None, NOW, 20)), 5)

    def test_public_snapshot_cancellations(self):
        base = ROOT / "tests/fixtures/open_data_20261023"
        s = json.loads((base / "schedule.json").read_text())
        u = rt.FeedMessage.FromString((base / "updates.pb").read_bytes())
        a = rt.FeedMessage.FromString((base / "alerts.pb").read_bytes())
        rows = build_board(s, u, a, datetime.fromtimestamp(u.header.timestamp, UTC), 3)
        self.assertEqual([r["numero"] for r in rows], ["862520", "862430", "862524"])
        self.assertTrue(all(r["supprime"] for r in rows))

    def test_public_snapshot_fills_five_rows_after_1519(self):
        base = ROOT / "tests/fixtures/open_data_20261023"
        s = json.loads((base / "schedule.json").read_text())
        u = rt.FeedMessage.FromString((base / "updates.pb").read_bytes())
        a = rt.FeedMessage.FromString((base / "alerts.pb").read_bytes())
        rows = build_board(s, u, a, NOW.replace(hour=15, minute=19))
        self.assertEqual([r["numero"] for r in rows],
                         ["862430", "862524", "862520", "862430", "862524"])
        self.assertEqual(rows[-1]["prevu"], "24/10 17:12")
        self.assertTrue(all(r["supprime"] for r in rows[:2]))
        self.assertTrue(all(not r["supprime"] for r in rows[2:]))


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        hass = MagicMock()
        async def execute(func, *args): return func(*args)
        hass.async_add_executor_job = execute
        client = OpenDataClient(hass, MagicMock())
        client.store = MagicMock(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        return client

    async def test_no_auth_request_headers(self):
        client = self.make_client()
        response = MagicMock(); response.read = AsyncMock(return_value=b"public")
        client.session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        self.assertEqual(await client._download(UPDATES_URL), b"public")
        kwargs = client.session.get.call_args.kwargs
        self.assertNotIn("auth", kwargs)
        self.assertNotIn("headers", kwargs)

    async def test_static_schedule_cached(self):
        client = self.make_client()
        current = datetime.now(UTC)
        async def download(url, timeout=30):
            return zip_schedule() if url == SCHEDULE_URL else feed(current).SerializeToString()
        client._download = AsyncMock(side_effect=download)
        await client.async_fetch(); await client.async_fetch()
        self.assertEqual(sum(c.args[0] == SCHEDULE_URL for c in client._download.call_args_list), 1)
        client.store.async_save.assert_awaited_once()

    async def test_cached_schedule_survives_restart(self):
        client = self.make_client()
        client.store.async_load.return_value = {"timestamp":datetime.now(UTC).timestamp(), "schedule":schedule()}
        client._download = AsyncMock(return_value=feed(datetime.now(UTC)).SerializeToString())
        await client.async_fetch()
        self.assertFalse(any(c.args[0] == SCHEDULE_URL for c in client._download.call_args_list))

    async def test_rt_failure_falls_back_with_warning(self):
        client = self.make_client()
        client.loaded = True; client.cache = {"timestamp":datetime.now(UTC).timestamp(), "schedule":schedule()}
        client._download = AsyncMock(side_effect=OpenDataError())
        data = await client.async_fetch()
        self.assertIsNone(data["updates"])
        self.assertIsNone(data["alerts"])
        self.assertEqual(len(data["warnings"]), 2)

    async def test_bad_static_file_returns_clear_error(self):
        client = self.make_client(); client._download = AsyncMock(return_value=b"not a zip")
        with self.assertRaises(OpenDataError): await client.async_fetch()

    async def test_old_static_cache_limited_to_48h(self):
        for hours, allowed in ((15, True), (49, False)):
            client = self.make_client(); client.loaded = True
            client.cache = {"timestamp":(datetime.now(UTC)-timedelta(hours=hours)).timestamp(), "schedule":schedule()}
            client._download = AsyncMock(side_effect=OpenDataError())
            if allowed:
                self.assertIn("Horaires en cache", (await client.async_fetch())["warnings"][0])
            else:
                with self.assertRaises(OpenDataError): await client.async_fetch()

    def test_stale_future_or_differential_feed_rejected(self):
        for offset in (-601, 301):
            with self.assertRaises(OpenDataError):
                OpenDataClient._decode(feed(NOW+timedelta(seconds=offset)).SerializeToString(), NOW)
        f = feed(); f.header.incrementality = rt.FeedHeader.DIFFERENTIAL
        with self.assertRaises(OpenDataError): OpenDataClient._decode(f.SerializeToString(), NOW)


class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        (Path(self.directory.name)/"custom_components").symlink_to(ROOT/"custom_components", target_is_directory=True)
        self.hass = HomeAssistant(self.directory.name); loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await self.hass.config_entries.async_initialize()
        self.patcher = patch("custom_components.sncf_epernon.config_flow.async_get_clientsession", return_value=MagicMock())
        self.patcher.start()
        self.entry = ConfigEntry(domain=DOMAIN, title="Épernon → Paris", data={"api_key":"obsolete-test-key"}, options={}, version=1, minor_version=1, source=SOURCE_USER, unique_id="87394114_87391003", discovery_keys=MappingProxyType({}), subentries_data=[])

    async def asyncTearDown(self):
        await self.hass.async_stop(); self.patcher.stop(); self.directory.cleanup()

    async def test_flow_without_key(self):
        with patch("custom_components.sncf_epernon.config_flow.OpenDataClient.async_fetch", new_callable=AsyncMock, return_value=snapshot()), patch("homeassistant.config_entries.ConfigEntry.async_setup", new_callable=AsyncMock, return_value=True):
            result = await self.hass.config_entries.flow.async_init(DOMAIN, context={"source":SOURCE_USER})
            self.assertEqual(len(result["data_schema"].schema), 0)
            result = await self.hass.config_entries.flow.async_configure(result["flow_id"], {})
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"], {"source":"open_data"})
            await self.hass.async_block_till_done()

    async def test_setup_unload_and_sensor(self):
        self.entry._async_set_state(self.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
        with patch("custom_components.sncf_epernon.async_get_clientsession", return_value=MagicMock()), patch("custom_components.sncf_epernon.open_data.OpenDataClient.async_fetch", new_callable=AsyncMock, return_value=snapshot()), patch.object(self.hass.config_entries,"async_forward_entry_setups",new_callable=AsyncMock):
            self.assertTrue(await async_setup_entry(self.hass,self.entry))
        sensor = SncfDeparturesSensor(self.entry.runtime_data)
        self.assertTrue(sensor.available)
        self.assertIn("trains",sensor.extra_state_attributes)
        self.assertEqual(sensor.unique_id,"87394114_87391003_departures")
        with patch.object(self.hass.config_entries,"async_unload_platforms",new_callable=AsyncMock,return_value=True):
            self.assertTrue(await async_unload_entry(self.hass,self.entry))
        await self.entry.runtime_data.async_shutdown()

    async def test_migration_removes_obsolete_token(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        self.assertTrue(await async_migrate_entry(self.hass,self.entry))
        self.assertEqual(self.entry.version,2)
        self.assertEqual(self.entry.data,{"source":"open_data"})
        self.assertEqual(self.entry.options["update_interval"],120)

    async def test_options(self):
        import voluptuous as vol
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        flow = SncfOptionsFlow(); flow.hass = self.hass; flow.handler = self.entry.entry_id
        schema = (await flow.async_step_init())["data_schema"]
        self.assertEqual(schema({"update_interval":120,"train_count":7})["train_count"],7)
        with self.assertRaises(vol.Invalid): schema({"update_interval":60,"train_count":5})

    async def test_coordinator_static_failure(self):
        client = MagicMock(async_fetch=AsyncMock(side_effect=OpenDataError("offline")))
        coordinator = SncfCoordinator(self.hass,self.entry,client)
        with self.assertRaises(UpdateFailed): await coordinator._async_update_data()
        await coordinator.async_shutdown()


class PackagingTests(unittest.TestCase):
    def test_structure(self):
        components = [p for p in (ROOT/"custom_components").iterdir() if p.is_dir() and not p.name.startswith("__")]
        self.assertEqual([p.name for p in components],[DOMAIN])
        manifest = json.loads((components[0]/"manifest.json").read_text())
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn("gtfs-realtime-bindings==3.0.0",manifest["requirements"])
        for language in ("en","fr"):
            text = json.loads((components[0]/"translations"/f"{language}.json").read_text())
            self.assertNotIn("api_key",str(text))


if __name__ == "__main__": unittest.main()
