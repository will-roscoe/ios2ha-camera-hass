"""The ios2ha-camera integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import Ios2haClient
from .const import CONF_URL, DOMAIN, PLATFORMS
from .coordinator import Ios2haCoordinator
from .frontend import async_register_card
from .services import async_register_actions, async_unregister_actions
from .views import Ios2haMediaView

type Ios2haConfigEntry = ConfigEntry[Ios2haCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Ios2haConfigEntry) -> bool:
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
    # The card, served by the integration itself and registered as a resource.
    await async_register_card(hass, str((await async_get_integration(hass, DOMAIN)).version))
    # Started after the platforms exist, so the first snapshot lands on entities
    # that are already there to receive it.
    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Ios2haConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [e for e in hass.config_entries.async_entries(DOMAIN)
              if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED]
    if unloaded and not others:
        async_unregister_actions(hass)
    return unloaded
