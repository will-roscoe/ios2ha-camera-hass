"""The ios2ha-camera integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Ios2haClient
from .const import CONF_URL, PLATFORMS
from .coordinator import Ios2haCoordinator

type Ios2haConfigEntry = ConfigEntry[Ios2haCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Ios2haConfigEntry) -> bool:
    client = Ios2haClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = Ios2haCoordinator(hass, entry, client)
    await coordinator.async_prepare()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Started after the platforms exist, so the first snapshot lands on entities
    # that are already there to receive it.
    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Ios2haConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
