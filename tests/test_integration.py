"""Offline tests using real Home Assistant classes and mocked SNCF responses."""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientError
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sncf_epernon.api import AccessDenied, InvalidAuth, RateLimited, SncfClient, SncfError
from custom_components.sncf_epernon.config_flow import SncfConfigFlow
from custom_components.sncf_epernon.const import DOMAIN
from custom_components.sncf_epernon.coordinator import SncfCoordinator
from custom_components.sncf_epernon.departures import PARIS, build_departures
from custom_components.sncf_epernon.sensor import SncfDeparturesSensor

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 23, 7, 0, tzinfo=PARIS)


def departure(time="070500", base=None, number="862406", freshness="realtime", alerts=()):
    return {
        "display_informations": {
            "headsign": number, "physical_mode": "Train régional ou Intercités",
            "direction": "Paris - Montparnasse - Hall 1 & 2",
            "links": [{"type": "disruption", "id": ident} for ident in alerts],
        },
        "stop_date_time": {
            "departure_date_time": f"20261023T{time}",
            "base_departure_date_time": f"20261023T{base or time}",
            "data_freshness": freshness,
        },
        "stop_point": {"id": "epernon"},
    }


def disruption(effect="NO_SERVICE", **overrides):
    return {
        "id": "c", "severity": {"effect": effect},
        "application_periods": [{"begin": "20261023T060000", "end": "20261023T100000"}],
        **overrides,
    }


def board(planned=(), live=(), impacts=(), now=NOW, count=5):
    return build_departures(
        {"departures": list(planned), "disruptions": list(impacts)},
        {"departures": list(live)}, now, count,
    )


class DepartureTests(unittest.TestCase):
    def test_on_time_deduplicates(self):
        rows = board([departure(freshness="base_schedule")], [departure()])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["statut"], "🟢 À l’heure")

    def test_theoretical_or_missing_realtime_is_not_green_or_cancelled(self):
        for live in ([], [departure(freshness="base_schedule")], [departure(freshness=None)]):
            with self.subTest(live=live):
                row = board([departure()], live)[0]
                self.assertEqual(row["statut"], "⚪ Horaire prévu")
                self.assertFalse(row["supprime"])

    def test_delay_retained_after_scheduled_departure(self):
        row = board([departure("065000")], [departure("071000", "065000")])[0]
        self.assertEqual(row["retard_minutes"], 20)
        self.assertEqual(row["estime"], "07:10")

    def test_cancellation_requires_link_and_period(self):
        self.assertTrue(board([departure(alerts=["c"])], impacts=[disruption()])[0]["supprime"])
        self.assertFalse(board([departure()], impacts=[disruption()])[0]["supprime"])
        self.assertFalse(board([departure(alerts=["c"])], impacts=[disruption(
            application_periods=[{"begin": "20261024T060000", "end": "20261024T100000"}]
        )])[0]["supprime"])

    def test_deleted_origin_only(self):
        for station, cancelled in (("epernon", True), ("other", False)):
            row = board([departure(alerts=["c"])], impacts=[disruption(
                "REDUCED_SERVICE", impacted_objects=[{"impacted_stops": [{
                    "stop_point": {"id": station}, "departure_status": "deleted",
                }]}]
            )])[0]
            self.assertEqual(row["supprime"], cancelled)

    def test_application_patterns_and_overnight(self):
        for begin, end, weekday, slot, applies in (
            ("20261023", "20261023", "friday", ("070000", "080000"), True),
            ("20261023", "20261023", "monday", ("070000", "080000"), False),
            ("20261022", "20261022", "thursday", ("230000", "080000"), True),
            ("20261023", "20261023", "friday", ("080000", "090000"), False),
        ):
            with self.subTest(weekday=weekday, slot=slot):
                impact = disruption(application_patterns=[{
                    "application_period": {"begin": begin, "end": end},
                    "week_pattern": {weekday: True},
                    "time_slots": [{"begin": slot[0], "end": slot[1]}],
                }])
                self.assertEqual(board([departure(alerts=["c"])], impacts=[impact])[0]["supprime"], applies)

    def test_past_trains_removed(self):
        self.assertEqual(board([departure("065000", alerts=["c"])], impacts=[disruption()]), [])
        self.assertEqual(board([], [departure("065000")]), [])

    def test_wrong_direction_and_bus_filtered(self):
        for key, value in (("direction", "Chartres"), ("physical_mode", "Autocar")):
            item = departure()
            item["display_informations"][key] = value
            self.assertEqual(board([item]), [])

    def test_extra_train_and_configurable_count(self):
        rows = board([], [departure(f"{h:02}0500", number=str(h)) for h in range(8, 16)], count=7)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["numero"], "8")

    def test_tomorrow_and_invalid_date(self):
        item = departure()
        item["stop_date_time"] = {"departure_date_time": "20261024T060100"}
        self.assertEqual(board([item])[0]["prevu"], "24/10 06:01")
        item["stop_date_time"] = {"departure_date_time": "invalid"}
        self.assertEqual(board([item]), [])

    def test_conflicting_disruption_prefers_realtime(self):
        rows = build_departures(
            {"departures": [departure(alerts=["c"])], "disruptions": [disruption()]},
            {"departures": [departure(alerts=["c"])], "disruptions": [disruption("UNKNOWN_EFFECT")]}, NOW,
        )
        self.assertFalse(rows[0]["supprime"])


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_requests_auth_and_aware_timestamp(self):
        session = MagicMock()
        response = MagicMock(status=200)
        response.json = AsyncMock(return_value={"departures": []})
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        result = await SncfClient(session, "test-key").async_fetch()
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(result["fetched_at"].tzinfo, UTC)
        self.assertEqual({c.kwargs["params"]["data_freshness"] for c in session.get.call_args_list}, {"base_schedule", "realtime"})
        self.assertTrue(all(c.kwargs["auth"].login == "test-key" for c in session.get.call_args_list))
        self.assertTrue(all(c.kwargs["auth"].password == "" for c in session.get.call_args_list))

    async def test_http_and_payload_errors(self):
        for status, payload, expected in (
            (401, {}, InvalidAuth), (403, {}, AccessDenied), (429, {}, RateLimited),
            (200, [], SncfError), (200, {"error": {"id": "no_solution"}}, SncfError),
            (200, {"departures": None}, SncfError),
        ):
            with self.subTest(status=status, payload=payload):
                session = MagicMock()
                response = MagicMock(status=status, headers={"Retry-After": "120"})
                response.json = AsyncMock(return_value=payload)
                session.get.return_value.__aenter__ = AsyncMock(return_value=response)
                with self.assertRaises(expected):
                    await SncfClient(session, "test-key").async_fetch()

    async def test_network_error(self):
        session = MagicMock()
        session.get.side_effect = ClientError("offline")
        with self.assertRaises(SncfError):
            await SncfClient(session, "test-key").async_fetch()


class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        (Path(self.directory.name) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        self.hass = HomeAssistant(self.directory.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await self.hass.config_entries.async_initialize()
        self.session_patch = patch(
            "custom_components.sncf_epernon.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        )
        self.session_patch.start()
        self.entry = ConfigEntry(
            domain=DOMAIN, title="Épernon → Paris", data={"api_key": "test-key"},
            options={}, version=1, minor_version=1, source=SOURCE_USER,
            unique_id="87394114_87391003", discovery_keys=MappingProxyType({}), subentries_data=[],
        )

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.session_patch.stop()
        self.directory.cleanup()

    async def test_discovery_and_user_flow(self):
        with patch("custom_components.sncf_epernon.config_flow.SncfClient.async_fetch", new_callable=AsyncMock, return_value={}), patch("homeassistant.config_entries.ConfigEntry.async_setup", new_callable=AsyncMock, return_value=True):
            result = await self.hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
            self.assertEqual(result["type"], "form")
            self.assertIn("api_key", result["data_schema"].schema)
            result = await self.hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "test-key"})
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"]["api_key"], "test-key")
            await self.hass.async_block_till_done()

    async def test_invalid_auth_in_form(self):
        flow = SncfConfigFlow()
        flow.hass = self.hass
        flow.context = {"source": SOURCE_USER}
        with patch("custom_components.sncf_epernon.config_flow.SncfClient.async_fetch", new_callable=AsyncMock, side_effect=InvalidAuth()):
            result = await flow.async_step_user({"api_key": "wrong"})
        self.assertEqual(result["errors"], {"base": "invalid_auth"})

    async def test_empty_key_does_not_contact_sncf(self):
        flow = SncfConfigFlow()
        flow.hass = self.hass
        with patch("custom_components.sncf_epernon.config_flow.SncfClient.async_fetch", new_callable=AsyncMock) as fetch:
            self.assertEqual(await flow._validate({"api_key": "  "}), {"base": "missing_api_key"})
            fetch.assert_not_awaited()

    async def test_forbidden_is_not_reported_as_invalid_key(self):
        flow = SncfConfigFlow()
        flow.hass = self.hass
        with patch("custom_components.sncf_epernon.config_flow.SncfClient.async_fetch", new_callable=AsyncMock, side_effect=AccessDenied()):
            self.assertEqual(await flow._validate({"api_key": "test-key"}), {"base": "access_denied"})

    async def test_key_trimmed_before_request(self):
        flow = SncfConfigFlow()
        flow.hass = self.hass
        data = {"api_key": "  test-key\n"}
        with patch("custom_components.sncf_epernon.config_flow.SncfClient") as client:
            client.return_value.async_fetch = AsyncMock(return_value={})
            self.assertEqual(await flow._validate(data), {})
            self.assertEqual(client.call_args.args[1], "test-key")
        self.assertEqual(data["api_key"], "test-key")

    async def test_options_restrict_polling_and_train_count(self):
        from custom_components.sncf_epernon.config_flow import SncfOptionsFlow
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        flow = SncfOptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        result = await flow.async_step_init()
        schema = result["data_schema"]
        self.assertEqual(schema({"update_interval": 60, "train_count": 7})["train_count"], 7)
        import voluptuous as vol
        with self.assertRaises(vol.Invalid):
            schema({"update_interval": 5, "train_count": 7})

    async def test_setup_and_unload(self):
        from custom_components.sncf_epernon import async_setup_entry, async_unload_entry
        self.entry._async_set_state(self.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
        snapshot = {"planned": {"departures": []}, "live": {"departures": []}, "fetched_at": NOW}
        with patch("custom_components.sncf_epernon.async_get_clientsession", return_value=MagicMock()), patch("custom_components.sncf_epernon.api.SncfClient.async_fetch", new_callable=AsyncMock, return_value=snapshot), patch.object(self.hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as forward:
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
            self.assertIsInstance(self.entry.runtime_data, SncfCoordinator)
            forward.assert_awaited_once()
        with patch.object(self.hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=True):
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
        await self.entry.runtime_data.async_shutdown()

    async def test_reauth_updates_key(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        flow = SncfConfigFlow()
        flow.hass = self.hass
        flow.context = {"source": "reauth", "entry_id": self.entry.entry_id}
        with patch("custom_components.sncf_epernon.config_flow.SncfClient.async_fetch", new_callable=AsyncMock, return_value={}), patch.object(self.hass.config_entries, "async_reload", new_callable=AsyncMock, return_value=True):
            result = await flow.async_step_reauth_confirm({"api_key": "new-key"})
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertEqual(self.entry.data["api_key"], "new-key")

    async def test_coordinator_errors_and_sensor(self):
        client = MagicMock()
        client.async_fetch = AsyncMock()
        coordinator = SncfCoordinator(self.hass, self.entry, client)
        for error, expected in ((InvalidAuth(), ConfigEntryAuthFailed), (AccessDenied(), UpdateFailed), (RateLimited(), UpdateFailed), (SncfError(), UpdateFailed)):
            client.async_fetch.side_effect = error
            with self.assertRaises(expected):
                await coordinator._async_update_data()
        coordinator.async_set_updated_data({"planned": {"departures": []}, "live": {"departures": []}, "fetched_at": NOW})
        sensor = SncfDeparturesSensor(coordinator)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.extra_state_attributes["trains"], [])
        self.assertEqual(sensor.native_value, NOW)
        coordinator.last_update_success = False
        self.assertFalse(sensor.available)
        await coordinator.async_shutdown()


class PackagingTests(unittest.TestCase):
    def test_hacs_structure(self):
        components = [p for p in (ROOT / "custom_components").iterdir() if p.is_dir() and not p.name.startswith("__")]
        self.assertEqual([p.name for p in components], [DOMAIN])
        manifest = json.loads((components[0] / "manifest.json").read_text())
        for field in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners"):
            self.assertTrue(manifest[field])
        self.assertTrue(manifest["config_flow"])
        self.assertEqual(manifest["domain"], DOMAIN)
        self.assertTrue(json.loads((ROOT / "hacs.json").read_text())["name"])
        for language in ("fr", "en"):
            text = json.loads((components[0] / "translations" / f"{language}.json").read_text())
            self.assertIn("invalid_auth", text["config"]["error"])
        self.assertTrue((components[0] / "brand/icon.png").is_file())


if __name__ == "__main__":
    unittest.main()
