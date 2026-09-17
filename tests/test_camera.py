from homeassistant.components.camera import async_get_image
from homeassistant.helpers import entity_registry as er

from .conftest import OBJECTS, SNAPSHOT


async def test_a_camera_per_media_descriptor_with_mqtt_ids(hass, setup):
    await setup([SNAPSHOT])
    reg = er.async_get(hass)
    for m in OBJECTS["media"]:
        assert reg.async_get(f"camera.ios2ha_camera_{m['id']}") is not None, m["id"]


async def test_every_described_camera_has_a_route_behind_it(hass, setup):
    """Since service 2.7.0 the screenshot has an HTTP route, so both camera
    descriptors are buildable and none is skipped. A descriptor with no media
    behind it would still be skipped rather than pointed at an invented path."""
    await setup([SNAPSHOT])
    described = {d["object_id"] for d in OBJECTS["objects"] if d["domain"] == "camera"}
    routed = {m["id"] for m in OBJECTS["media"]}
    assert described - routed == set()
    assert hass.states.get("camera.ios2ha_camera_screenshot") is not None


async def test_the_screenshot_camera_keeps_its_descriptor_name_and_category(hass, setup):
    """It has a descriptor, so the media does not get to name it."""
    await setup([SNAPSHOT])
    st = hass.states.get("camera.ios2ha_camera_screenshot")
    assert st.attributes["friendly_name"] == "iPhone Camera Screenshot"


async def test_the_screenshot_camera_serves_its_own_image_not_the_still(
    hass, setup, aioclient_mock
):
    """It is a snapshot in its own right, so it must not borrow the still's
    thumbnail the way a stream does."""
    await setup([SNAPSHOT])
    aioclient_mock.get(
        "http://camera-host.lan:8099/api/v1/snapshot/screenshot", content=b"\x89PNG\r\n\x1a\n"
    )
    image = await async_get_image(hass, "camera.ios2ha_camera_screenshot")
    assert image.content == b"\x89PNG\r\n\x1a\n"


async def test_every_camera_thumbnail_uses_the_snapshot_route(hass, setup, aioclient_mock):
    await setup([SNAPSHOT])
    aioclient_mock.get("http://camera-host.lan:8099/api/v1/snapshot/still", content=b"\xff\xd8jpeg")
    # Not the screenshot: that is a snapshot of its own and serves its own image.
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


def test_the_thumbnail_source_is_the_still_whatever_the_order():
    """Two snapshots exist now; only the still shows what a stream shows."""
    from custom_components.ios2ha_camera.camera import _thumbnail_source

    shot = {"id": "screenshot", "kind": "snapshot", "holds_phone": False}
    still = {"id": "still", "kind": "snapshot", "holds_phone": False}
    live = {"id": "live", "kind": "stream", "holds_phone": True}
    assert _thumbnail_source([shot, still, live]) is still
    assert _thumbnail_source([still, shot, live]) is still
    # No still at all: fall back to any snapshot rather than none.
    assert _thumbnail_source([shot, live]) is shot
    assert _thumbnail_source([live]) is None
