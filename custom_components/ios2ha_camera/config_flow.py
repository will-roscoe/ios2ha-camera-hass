"""Config flow: one question, the address."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import ApiDisabled, CannotConnect, Ios2haClient, NotIos2ha, UnsupportedApi
from .const import CONF_URL, DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_URL): str})


def normalise(url: str) -> str:
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    return url


class Ios2haConfigFlow(ConfigFlow, domain=DOMAIN):
    """There is no authentication, so the address is the whole configuration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            url = normalise(user_input[CONF_URL])
            client = Ios2haClient(async_get_clientsession(self.hass), url)
            try:
                info = await client.get_info()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ApiDisabled:
                errors["base"] = "api_disabled"
            except UnsupportedApi as err:
                errors["base"] = "unsupported_api"
                placeholders["found"] = str(err.found)
            except NotIos2ha:
                errors["base"] = "not_ios2ha"
            else:
                await self.async_set_unique_id("-".join(info["device"]["identifiers"]))
                self._abort_if_unique_id_configured(updates={CONF_URL: url})
                return self.async_create_entry(title=info["device"]["name"], data={CONF_URL: url})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input or {}),
            errors=errors,
            description_placeholders=placeholders or {"found": ""},
        )
