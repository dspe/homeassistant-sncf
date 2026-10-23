"""Download the public SNCF files without credentials, cache the daily schedule."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from zipfile import BadZipFile

from aiohttp import ClientError, ClientSession, ClientTimeout
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as rt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import ALERTS_URL, SCHEDULE_URL, UPDATES_URL
from .gtfs import parse_schedule


class OpenDataError(Exception):
    """The public SNCF schedule cannot be loaded."""


class OpenDataClient:
    """Download national RT feeds every 2 minutes, static schedule every 12 hours."""

    def __init__(self, hass: HomeAssistant, session: ClientSession) -> None:
        self.hass = hass
        self.session = session
        self.store = Store(hass, 1, "sncf_epernon_open_schedule")
        self.cache = None
        self.loaded = False
        self.next_schedule_attempt = 0

    async def _download(self, url, timeout=30):
        try:
            async with self.session.get(url, timeout=ClientTimeout(total=timeout)) as response:
                response.raise_for_status()
                return await response.read()
        except (ClientError, TimeoutError) as err:
            raise OpenDataError("Flux SNCF public inaccessible") from err

    async def _schedule(self, now):
        if not self.loaded:
            self.cache = await self.store.async_load()
            self.loaded = True
        if self.cache and now.timestamp() < self.next_schedule_attempt and now.timestamp() - self.cache["timestamp"] <= 172800:
            return
        if self.cache and now.timestamp() - self.cache["timestamp"] < 43200:
            return
        try:
            data = await self._download(SCHEDULE_URL, 90)
            schedule = await self.hass.async_add_executor_job(parse_schedule, data)
        except (OpenDataError, ValueError, KeyError, OSError, BadZipFile) as err:
            if not self.cache or now.timestamp() - self.cache["timestamp"] > 172800:
                raise OpenDataError("Impossible de charger les horaires SNCF publics") from err
            self.next_schedule_attempt = now.timestamp() + 3600
            return
        self.cache = {"timestamp": now.timestamp(), "schedule": schedule}
        await self.store.async_save(self.cache)

    @staticmethod
    def _decode(content, now):
        feed = rt.FeedMessage.FromString(content)
        if not feed.IsInitialized() or feed.header.incrementality != rt.FeedHeader.FULL_DATASET:
            raise OpenDataError("Flux GTFS-RT incomplet")
        age = now.timestamp() - feed.header.timestamp
        if not feed.header.HasField("timestamp") or not -300 <= age <= 600:
            raise OpenDataError("Flux temps réel trop ancien")
        return feed

    async def async_fetch(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        await self._schedule(now)
        contents = await asyncio.gather(
            self._download(UPDATES_URL), self._download(ALERTS_URL), return_exceptions=True
        )
        feeds, warnings = [], []
        if now.timestamp() - self.cache["timestamp"] >= 43200:
            warnings.append("Horaires en cache : actualisation différée")
        for label, content in zip(("prévisions", "perturbations"), contents, strict=True):
            try:
                if isinstance(content, BaseException):
                    raise OpenDataError() from content
                feeds.append(self._decode(content, datetime.now(UTC)))
            except (OpenDataError, DecodeError):
                feeds.append(None)
                warnings.append(f"Flux {label} indisponible ou périmé")
        return {
            "schedule": self.cache["schedule"], "updates": feeds[0], "alerts": feeds[1],
            "fetched_at": datetime.now(UTC), "warnings": warnings,
            "schedule_updated_at": datetime.fromtimestamp(self.cache["timestamp"], UTC).isoformat(),
            "realtime_updated_at": datetime.fromtimestamp(feeds[0].header.timestamp, UTC).isoformat() if feeds[0] else None,
        }
