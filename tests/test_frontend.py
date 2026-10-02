"""The card ships with the integration: served by it, and registered as a resource."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ios2ha_camera.api import CannotConnect
from custom_components.ios2ha_camera.const import DOMAIN

from .conftest import SNAPSHOT

CARD = "/ios2ha_camera/ios2ha-camera-card.js"


async def test_the_card_is_served_by_the_integration(hass, setup, hass_client_no_auth):
    await setup([SNAPSHOT])
    client = await hass_client_no_auth()
    resp = await client.get(CARD)
    assert resp.status == 200
    body = await resp.text()
    assert '"ios2ha-camera-card"' in body


async def test_the_card_is_served_while_the_service_is_down(hass, hass_client_no_auth):
    # A dashboard that holds the card must still find it while Home Assistant
    # waits for the service, or it shows "custom element doesn't exist" instead.
    entry = MockConfigEntry(domain=DOMAIN, data={"url": "http://camera-host.lan:8099"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.ios2ha_camera.api.Ios2haClient.get_info",
        AsyncMock(side_effect=CannotConnect("down")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    client = await hass_client_no_auth()
    assert (await client.get(CARD)).status == 200


async def test_a_card_that_cannot_register_leaves_the_camera_working(hass, setup):
    with patch(
        "custom_components.ios2ha_camera.async_register_card",
        AsyncMock(side_effect=RuntimeError("resource store unavailable")),
    ):
        entry = await setup([SNAPSHOT])
    assert entry.state is ConfigEntryState.LOADED
