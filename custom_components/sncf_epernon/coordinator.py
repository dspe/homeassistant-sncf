"""Coordinate SNCF polling."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InvalidAuth, RateLimited, SncfClient, SncfError
from .const import CONF_COUNT, CONF_INTERVAL, DEFAULT_COUNT, DEFAULT_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SncfCoordinator(DataUpdateCoordinator[dict]):
    """Keep one pair of SNCF requests per polling interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SncfClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )
        self.client = client
        self.train_count = entry.options.get(CONF_COUNT, DEFAULT_COUNT)

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_fetch()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("La clé API SNCF a été refusée") from err
        except RateLimited as err:
            raise UpdateFailed("Quota SNCF atteint", retry_after=err.retry_after) from err
        except SncfError as err:
            raise UpdateFailed(str(err)) from err
