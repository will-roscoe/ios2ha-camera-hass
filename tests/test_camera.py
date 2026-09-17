from homeassistant.components.camera import async_get_image
from homeassistant.helpers import entity_registry as er

from .conftest import OBJECTS, SNAPSHOT


async def test_a_camera_per_media_descriptor_with_mqtt_ids(hass, setup):
    await setup([SNAPSHOT])
    reg = er.async_get(hass)
    for m in OBJECTS["media"]:
        assert reg.async_get(f"camera.ios2ha_camera_{m['id']}") is not None, m["id"]


async def test_a_camera_the_service_offers_no_route_for_is_skipped(hass, setup):
    """`screenshot` is a camera descriptor published only as a retained MQTT PNG.

    There is no HTTP route behind it, and inventing one would mean guessing at a
    path the service does not serve. It is a README-documented gap, not an
    entity showing a permanent error.
    """
    await setup([SNAPSHOT])
    described = {d["object_id"] for d in OBJECTS["objects"] if d["domain"] == "camera"}
    routed = {m["id"] for m in OBJECTS["media"]}
    assert described - routed == {"screenshot"}
    assert hass.states.get("camera.ios2ha_camera_screenshot") is None


async def test_every_camera_thumbnail_uses_the_snapshot_route(hass, setup, aioclient_mock):
    await setup([SNAPSHOT])
    aioclient_mock.get("http://camera-host.lan:8099/api/v1/snapshot/still", content=b"\xff\xd8jpeg")
    for cam in ("still", "live", "stacked"):
        image = await async_get_image(hass, f"camera.ios2ha_camera_{cam}")
        assert image.content == b"\xff\xd8jpeg"
    urls = {str(call[1]) for call in aioclient_mock.mock_calls}
    assert urls == {"http://camera-host.lan:8099/api/v1/snapshot/still"}


async def test_the_main_camera_is_named_after_the_device(hass, setup):
    await setup([SNAPSHOT])
    assert (
        hass.states.get("camera.ios2ha_camera_still").attributes["friendly_name"] == "iPhone Camera"
    )


async def test_a_stream_camera_is_named_after_its_media(hass, setup):
    await setup([SNAPSHOT])
    assert (
        hass.states.get("camera.ios2ha_camera_live").attributes["friendly_name"]
        == "iPhone Camera Live"
    )
