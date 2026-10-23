"""Coordinate downloads of the public SNCF data."""

from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import CONF_COUNT, CONF_INTERVAL, DEFAULT_COUNT, DEFAULT_INTERVAL, DOMAIN
from .open_data import OpenDataClient, OpenDataError

_LOGGER = logging.getLogger(__name__)


class SncfCoordinator(DataUpdateCoordinator[dict]):
    """Refresh the public feeds, retaining theoretical schedules on RT failure."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: OpenDataClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=max(DEFAULT_INTERVAL, entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL))))
        self.client = client
        self.train_count = entry.options.get(CONF_COUNT, DEFAULT_COUNT)

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_fetch()
        except OpenDataError as err:
            raise UpdateFailed(str(err)) from err
