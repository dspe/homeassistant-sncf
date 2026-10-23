"""Configure the public SNCF source without any API key."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_COUNT, CONF_INTERVAL, DEFAULT_COUNT, DEFAULT_INTERVAL, DOMAIN, ROUTE_ID, TITLE
from .open_data import OpenDataClient, OpenDataError


class SncfConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One fixed route, no credentials."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return SncfOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(ROUTE_ID)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            try:
                await OpenDataClient(self.hass, async_get_clientsession(self.hass)).async_fetch()
            except OpenDataError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=TITLE, data={"source": "open_data"})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}), errors=errors)

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data_updates={"source": "open_data"}
            )
        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema({}))


class SncfOptionsFlow(config_entries.OptionsFlow):
    """Polling frequency and number of departures."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required(CONF_INTERVAL, default=max(DEFAULT_INTERVAL, options.get(CONF_INTERVAL, DEFAULT_INTERVAL))):
                vol.All(vol.Coerce(int), vol.Range(min=DEFAULT_INTERVAL, max=3600)),
            vol.Required(CONF_COUNT, default=options.get(CONF_COUNT, DEFAULT_COUNT)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
