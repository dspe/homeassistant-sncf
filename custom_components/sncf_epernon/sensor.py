"""Expose the SNCF departure list to Lovelace."""

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ROUTE_ID, TITLE
from .coordinator import SncfCoordinator
from .departures import build_departures

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SncfDeparturesSensor(entry.runtime_data)])


class SncfDeparturesSensor(CoordinatorEntity[SncfCoordinator], SensorEntity):
    """Timestamp of the API fetch, with the train list as an attribute."""

    _attr_name = "SNCF Epernon Paris"
    _attr_unique_id = f"{ROUTE_ID}_departures"
    _attr_icon = "mdi:train"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_attribution = "Données SNCF"
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, ROUTE_ID)}, name=TITLE,
        manufacturer="SNCF", entry_type=DeviceEntryType.SERVICE,
    )

    @property
    def native_value(self) -> datetime:
        return self.coordinator.data["fetched_at"]

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "trains": build_departures(
                data["planned"], data["live"], datetime.now(UTC), self.coordinator.train_count
            ),
            "gare_depart": "Épernon",
            "destination": "Paris-Montparnasse",
        }
