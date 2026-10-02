"""The ios2ha-camera integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import Ios2haClient
from .bubble import async_refresh as async_refresh_bubble_module
from .const import CONF_URL, DOMAIN, PLATFORMS
from .coordinator import Ios2haCoordinator
from .frontend import async_register_card
from .services import async_register_actions, async_unregister_actions
from .views import Ios2haMediaView

_LOGGER = logging.getLogger(__name__)

type Ios2haConfigEntry = ConfigEntry[Ios2haCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Ios2haConfigEntry) -> bool:
    version = str((await async_get_integration(hass, DOMAIN)).version)
    # The card first, served by the integration and registered as a resource: a
    # dashboard that holds it must find it even while setup waits for the
    # service, and a card that cannot register must not take the camera down.
    try:
        await async_register_card(hass, version)
    except Exception:
        _LOGGER.exception("the card could not be registered")
    # An update brings an installed Bubble Card module up to this release.
    try:
        await async_refresh_bubble_module(hass, version)
    except Exception:
        _LOGGER.exception("the Bubble Card module could not be updated")
    client = Ios2haClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = Ios2haCoordinator(hass, entry, client)
    await coordinator.async_prepare()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The service's actions, as Home Assistant actions (services.py).
    async_register_actions(hass, coordinator)
    # Once per Home Assistant run: the view serves every camera's video media.
    if not hass.data.get(f"{DOMAIN}_view"):
        hass.http.register_view(Ios2haMediaView(hass))
        hass.data[f"{DOMAIN}_view"] = True
    # Started after the platforms exist, so the first snapshot lands on entities
    # that are already there to receive it.
    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Ios2haConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
    ]
    if unloaded and not others:
        async_unregister_actions(hass)
    return unloaded
