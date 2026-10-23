"""Configure the API key from the Home Assistant UI."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import InvalidAuth, RateLimited, SncfClient, SncfError
from .const import (
    CONF_COUNT, CONF_INTERVAL, DEFAULT_COUNT, DEFAULT_INTERVAL, DOMAIN, ROUTE_ID, TITLE,
)

KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD)
)})


class SncfConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One Épernon to Paris route per installation."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return SncfOptionsFlow()

    async def _validate(self, data: dict[str, Any]) -> dict[str, str]:
        key = data[CONF_API_KEY].strip()
        if not key:
            return {"base": "invalid_auth"}
        try:
            await SncfClient(async_get_clientsession(self.hass), key).async_fetch()
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except RateLimited:
            return {"base": "rate_limited"}
        except SncfError:
            return {"base": "cannot_connect"}
        data[CONF_API_KEY] = key
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(ROUTE_ID)
        self._abort_if_unique_id_configured()
        errors = await self._validate(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title=TITLE, data=user_input)
        return self.async_show_form(step_id="user", data_schema=KEY_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = await self._validate(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=user_input
            )
        return self.async_show_form(step_id="reauth_confirm", data_schema=KEY_SCHEMA, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = await self._validate(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data_updates=user_input
            )
        return self.async_show_form(step_id="reconfigure", data_schema=KEY_SCHEMA, errors=errors)


class SncfOptionsFlow(config_entries.OptionsFlow):
    """Polling frequency and number of trains."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required(CONF_INTERVAL, default=options.get(CONF_INTERVAL, DEFAULT_INTERVAL)):
                vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
            vol.Required(CONF_COUNT, default=options.get(CONF_COUNT, DEFAULT_COUNT)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
