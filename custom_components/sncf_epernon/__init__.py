"""SNCF Épernon to Paris departure board."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .open_data import OpenDataClient
from .const import CONF_INTERVAL, DEFAULT_INTERVAL
from .coordinator import SncfCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Fetch initial data, then add entities."""
    coordinator = SncfCoordinator(
        hass, entry, OpenDataClient(hass, async_get_clientsession(hass))
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and polling listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Switch existing entries to open data and discard the obsolete API key."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        options = dict(entry.options)
        options[CONF_INTERVAL] = max(DEFAULT_INTERVAL, options.get(CONF_INTERVAL, DEFAULT_INTERVAL))
        hass.config_entries.async_update_entry(
            entry, version=2, data={"source": "open_data"}, options=options
        )
    return True
