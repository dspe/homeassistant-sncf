"""Small authenticated SNCF API client."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import BasicAuth, ClientError, ClientSession, ClientTimeout

from .const import API_URL
from .departures import PARIS


class SncfError(Exception):
    """SNCF response cannot be used."""


class InvalidAuth(SncfError):
    """API key rejected."""


class RateLimited(SncfError):
    """SNCF request quota reached."""

    def __init__(self, retry_after: int = 300) -> None:
        super().__init__("Quota SNCF atteint")
        self.retry_after = retry_after


class SncfClient:
    """Fetch planned and realtime departures with a shared HA session."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._auth = BasicAuth(api_key, "")

    async def _fetch(self, freshness: str, start: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                API_URL,
                auth=self._auth,
                params={
                    "from_datetime": start, "duration": 97200, "count": 80,
                    "depth": 2, "data_freshness": freshness, "disable_geojson": "true",
                },
                timeout=ClientTimeout(total=20),
            ) as response:
                if response.status in (401, 403):
                    raise InvalidAuth("Clé SNCF refusée")
                if response.status == 429:
                    retry = response.headers.get("Retry-After", "300")
                    raise RateLimited(max(60, int(retry)) if retry.isdecimal() else 300)
                response.raise_for_status()
                payload = await response.json()
        except (ClientError, TimeoutError, ValueError) as err:
            raise SncfError("Impossible de récupérer les départs SNCF") from err
        if not isinstance(payload, dict):
            raise SncfError("Réponse SNCF inattendue")
        if payload.get("error") or not isinstance(payload.get("departures"), list):
            raise SncfError("Liste des départs absente de la réponse SNCF")
        return payload

    async def async_fetch(self) -> dict[str, Any]:
        """Return an atomic pair: never mix a failed response with old data."""
        start = (datetime.now(PARIS) - timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")
        results = await asyncio.gather(
            self._fetch("base_schedule", start), self._fetch("realtime", start),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        planned, live = results
        return {"planned": planned, "live": live, "fetched_at": datetime.now(UTC)}
