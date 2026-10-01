"""The service's actions as Home Assistant actions, built from their descriptors.

`build_timelapse` is the first, but nothing here is about timelapses: whatever the
service declares in /objects becomes `ios2ha_camera.<name>`, with a form built from
its fields, and the call goes to the same control route as every other write.
"""
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.ios2ha_camera.api import ControlRejected
from custom_components.ios2ha_camera.const import DOMAIN
from custom_components.ios2ha_camera.services import target

from .conftest import OBJECTS, SNAPSHOT, _events_then_wait, _get_info

POST = "custom_components.ios2ha_camera.api.Ios2haClient.post_control"


async def test_every_declared_action_is_registered(hass, setup):
    await setup([SNAPSHOT])
    assert hass.services.has_service(DOMAIN, "build_timelapse")
    assert hass.services.has_service(DOMAIN, "delete_timelapse")


async def test_a_call_posts_the_fields_given_and_nothing_else(hass, setup):
    await setup([SNAPSHOT])
    post = AsyncMock(return_value={"ok": True, "name": "build_timelapse"})
    with patch(POST, post):
        response = await hass.services.async_call(
            DOMAIN, "build_timelapse", {"range": "7d", "fps": 24},
            blocking=True, return_response=True)
    post.assert_awaited_once_with("build_timelapse", {"range": "7d", "fps": 24})
    assert response["ok"] is True


async def test_a_time_is_sent_with_home_assistants_zone(hass, setup):
    await setup([SNAPSHOT])
    post = AsyncMock(return_value={"ok": True})
    with patch(POST, post):
        await hass.services.async_call(
            DOMAIN, "build_timelapse", {"start": "2026-09-28 18:00:00", "name": "storm"},
            blocking=True)
    sent = post.await_args.args[1]
    when = dt_util.parse_datetime(sent["start"])
    assert when.tzinfo is not None
    assert when == dt_util.parse_datetime("2026-09-28 18:00:00").replace(
        tzinfo=dt_util.get_default_time_zone())
    assert sent["name"] == "storm"


async def test_the_services_refusal_is_the_error(hass, setup):
    await setup([SNAPSHOT])
    with patch(POST, AsyncMock(side_effect=ControlRejected(400, "unknown key 'colour'"))), \
            pytest.raises(ServiceValidationError, match="unknown key 'colour'"):
        await hass.services.async_call(DOMAIN, "build_timelapse", {"range": "7d"}, blocking=True)


async def test_a_value_outside_its_field_is_refused_before_it_is_sent(hass, setup):
    await setup([SNAPSHOT])
    post = AsyncMock()
    with patch(POST, post), pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "build_timelapse", {"fps": 0}, blocking=True)
    post.assert_not_awaited()


async def test_a_device_chooses_the_camera(hass, setup):
    entry = await setup([SNAPSHOT])
    device = next(iter(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)))
    assert target(hass, device.id) is entry.runtime_data
    with pytest.raises(ServiceValidationError, match="not an ios2ha"):
        target(hass, "no-such-device")


async def test_with_two_cameras_a_device_is_needed(hass, setup):
    await setup([SNAPSHOT])
    other = MockConfigEntry(domain=DOMAIN, data={"url": "http://other:8099"}, unique_id="other",
                            state=ConfigEntryState.LOADED)
    other.add_to_hass(hass)
    with pytest.raises(ServiceValidationError, match="device"):
        target(hass, None)


async def test_a_service_without_actions_registers_none(hass):
    """A service older than 2.16.0 declares none; the integration loads as before."""
    without = {k: v for k, v in OBJECTS.items() if k != "actions"}
    entry = MockConfigEntry(domain=DOMAIN, data={"url": "http://camera-host.lan:8099"},
                            unique_id="ios2ha_camera", title="iPhone Camera")
    entry.add_to_hass(hass)
    base = "custom_components.ios2ha_camera.api.Ios2haClient"
    with (patch(f"{base}.get_info", _get_info),
          patch(f"{base}.get_objects", AsyncMock(return_value=without)),
          patch(f"{base}.events", lambda self: _events_then_wait([SNAPSHOT])())):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert not hass.services.has_service(DOMAIN, "build_timelapse")


async def test_the_actions_go_with_the_last_entry(hass, setup):
    entry = await setup([SNAPSHOT])
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "build_timelapse")
