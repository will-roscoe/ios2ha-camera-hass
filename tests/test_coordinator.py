import asyncio
from unittest.mock import AsyncMock, MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ios2ha_camera.api import CannotConnect, Event
from custom_components.ios2ha_camera.const import DOMAIN
from custom_components.ios2ha_camera.coordinator import Ios2haCoordinator

from .conftest import load_fixture_json


def _client(events):
    c = MagicMock()
    c.get_info = AsyncMock(return_value=load_fixture_json("info"))
    c.get_objects = AsyncMock(return_value=load_fixture_json("objects"))
    c.routes = load_fixture_json("info")["routes"]

    async def gen():
        for e in events:
            if isinstance(e, Exception):
                raise e
            yield e
        await asyncio.sleep(3600)

    c.events = MagicMock(side_effect=lambda: gen())
    return c


def _entry(hass):
    e = MockConfigEntry(
        domain=DOMAIN, data={"url": "http://camera-host.lan:8099"}, unique_id="ios2ha_camera"
    )
    e.add_to_hass(hass)
    return e


async def test_snapshot_replaces_state_and_a_delta_merges(hass):
    info = load_fixture_json("info")
    v = info["objects_version"]
    client = _client(
        [
            Event("snapshot", {"objects_version": v, "state": {"a": 1, "b": 2}}),
            Event("state", {"state": {"b": 3}}),
            Event("something_new", {"z": 1}),
        ]
    )
    coord = Ios2haCoordinator(hass, _entry(hass), client)
    await coord.async_prepare()
    coord.start()
    await hass.async_block_till_done()
    assert coord.data == {"a": 1, "b": 3}
    assert coord.connected
    await coord.async_stop()


async def test_a_reconnect_snapshot_drops_keys_the_old_state_had(hass):
    v = load_fixture_json("info")["objects_version"]
    client = _client(
        [
            Event("snapshot", {"objects_version": v, "state": {"a": 1, "gone": 9}}),
            CannotConnect("dropped"),
        ]
    )
    coord = Ios2haCoordinator(hass, _entry(hass), client)
    coord.reconnect_delay = lambda attempt: 0  # no waiting in tests
    await coord.async_prepare()
    coord.start()
    await hass.async_block_till_done()
    client.events.side_effect = lambda: _client(
        [Event("snapshot", {"objects_version": v, "state": {"a": 2}})]
    ).events()
    for _ in range(5):
        await asyncio.sleep(0)
        await hass.async_block_till_done()
    assert coord.data == {"a": 2}
    await coord.async_stop()


async def test_descriptors_are_cached_and_reused_when_the_version_matches(hass):
    entry = _entry(hass)
    first = Ios2haCoordinator(hass, entry, _client([]))
    await first.async_prepare()
    assert first.client.get_objects.await_count == 1
    second_client = _client([])
    second = Ios2haCoordinator(hass, entry, second_client)
    await second.async_prepare()
    assert second_client.get_objects.await_count == 0
    assert len(second.objects) == len(first.objects) == 86


async def test_an_unreachable_service_with_a_cache_still_prepares(hass):
    entry = _entry(hass)
    await Ios2haCoordinator(hass, entry, _client([])).async_prepare()
    down = _client([])
    down.get_info = AsyncMock(side_effect=CannotConnect("down"))
    coord = Ios2haCoordinator(hass, entry, down)
    await coord.async_prepare()
    assert len(coord.objects) == 86 and not coord.connected


def test_descriptors_filter_by_domain_and_skip_unknown_ones(hass):
    coord = Ios2haCoordinator.__new__(Ios2haCoordinator)
    coord.objects = [
        {"domain": "sensor", "object_id": "a"},
        {"domain": "hologram", "object_id": "b"},
    ]
    assert coord.descriptors("sensor") == [{"domain": "sensor", "object_id": "a"}]
    assert coord.descriptors("hologram") == [{"domain": "hologram", "object_id": "b"}]
