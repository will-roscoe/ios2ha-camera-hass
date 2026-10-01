"""Serve and register the integration's Lovelace card.

Serving the file is not enough for `custom:ios2ha-camera-card` to exist: the browser
loads it only as a Lovelace resource. In storage mode it is added to the resource
collection, as if by hand under Settings -> Dashboards -> Resources; in YAML mode
that collection is read-only, so it is injected as an extra frontend module. The
version rides in the query string, so an update is never hidden by a cache.
(The pattern of the sibling intercom integration, which runs the same way.)
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "ios2ha-camera-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
_REGISTERED = f"{DOMAIN}_card_registered"


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """Serve the card and register it with the frontend, once per Home Assistant run."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    from homeassistant.components.http import StaticPathConfig

    path = str(Path(__file__).parent / "www" / CARD_FILENAME)
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, path, cache_headers=False)]
        )
    except (RuntimeError, ValueError) as err:  # already there, after a reload
        _LOGGER.debug("card path not (re)registered: %s", err)
    await _async_register_resource(hass, f"{CARD_URL}?v={version}")


async def _async_register_resource(hass: HomeAssistant, url: str) -> None:
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
    except ImportError:
        ResourceStorageCollection = None  # noqa: N806
    if (
        resources is None
        or ResourceStorageCollection is None
        or not isinstance(resources, ResourceStorageCollection)
    ):
        from homeassistant.components.frontend import add_extra_js_url

        try:
            add_extra_js_url(hass, url)
        except KeyError:  # the frontend is not loaded (a test, or a headless setup)
            _LOGGER.debug("no frontend to add the card to")
        return
    await resources.async_get_info()
    for item in resources.async_items():
        if item.get("url", "").split("?", 1)[0] == CARD_URL:
            if item.get("url") != url:
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
            return
    await resources.async_create_item({"res_type": "module", "url": url})
    _LOGGER.info("registered Lovelace resource %s", url)
