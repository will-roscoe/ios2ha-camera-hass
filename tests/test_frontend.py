"""The card ships with the integration: served by it, and registered as a resource."""
from .conftest import SNAPSHOT


async def test_the_card_is_served_by_the_integration(hass, setup, hass_client_no_auth):
    await setup([SNAPSHOT])
    client = await hass_client_no_auth()
    resp = await client.get("/ios2ha_camera/ios2ha-camera-card.js")
    assert resp.status == 200
    body = await resp.text()
    assert 'customElements.define("ios2ha-camera-card"' in body
