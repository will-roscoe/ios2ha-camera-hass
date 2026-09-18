from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.ios2ha_camera.api import Event
from custom_components.ios2ha_camera.const import DOMAIN

from .conftest import INFO, OBJECTS, SNAPSHOT, STATE


async def test_every_sensor_gets_the_mqtt_entity_id(hass, setup):
    await setup([SNAPSHOT])
    reg = er.async_get(hass)
    for d in OBJECTS["objects"]:
        if d["domain"] in ("sensor", "binary_sensor"):
            eid = f"{d['domain']}.ios2ha_camera_{d['object_id']}"
            assert reg.async_get(eid) is not None, eid


async def test_sensor_state_attributes_come_from_the_descriptor(hass, setup):
    await setup([SNAPSHOT])
    st = hass.states.get("sensor.ios2ha_camera_stream_state")
    assert st.state == STATE["stream_state"]
    assert st.attributes["options"] == next(
        d["options"] for d in OBJECTS["objects"] if d["object_id"] == "stream_state"
    )
    online = hass.states.get("binary_sensor.ios2ha_camera_camera_online")
    assert online.state == ("on" if STATE["camera_online"] else "off")


async def test_a_delta_updates_only_its_entity(hass, setup):
    await setup([SNAPSHOT, Event("state", {"state": {"stream_state": "stalled"}})])
    assert hass.states.get("sensor.ios2ha_camera_stream_state").state == "stalled"


async def test_before_any_snapshot_everything_is_unavailable(hass, setup):
    await setup([])
    assert hass.states.get("sensor.ios2ha_camera_stream_state").state == STATE_UNAVAILABLE


async def test_one_device_named_after_the_service(hass, setup):
    entry = await setup([SNAPSHOT])
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "iPhone Camera"
    assert (DOMAIN, "ios2ha_camera") in devices[0].identifiers
    assert devices[0].sw_version == INFO["device"]["sw_version"]


async def test_a_timestamp_sensor_becomes_a_datetime(hass, setup):
    """`last_frame` is declared device_class timestamp, and Home Assistant wants
    a datetime for those; the service sends ISO 8601 text over JSON, which has
    no datetime of its own. Left as a string it is rejected outright and the
    entity carries no state at all."""
    from datetime import datetime

    await setup([SNAPSHOT])
    st = hass.states.get("sensor.ios2ha_camera_last_frame")
    assert st.state not in ("unknown", "unavailable"), st.state
    # Home Assistant renders a timestamp state to whole seconds.
    assert datetime.fromisoformat(st.state) == datetime.fromisoformat(STATE["last_frame"]).replace(
        microsecond=0
    )


async def test_unparseable_timestamp_text_is_not_a_crash(hass, setup):
    await setup([SNAPSHOT, Event("state", {"state": {"last_frame": "not a time"}})])
    assert hass.states.get("sensor.ios2ha_camera_last_frame").state == "unknown"


async def test_a_control_with_no_value_yet_is_still_settable(hass, setup):
    """The three black level overrides carry a state_key the service only
    publishes once the override is set, so before that they have no value.

    That must read as unknown, not unavailable: an unavailable entity cannot be
    written to, and the service would accept the write perfectly well -- which
    is exactly how the setting gets its first value. Under MQTT these showed as
    unknown and stayed settable, and the two paths must not differ.
    """
    await setup([SNAPSHOT])
    assert "black_level_0" not in STATE, "fixture no longer covers the case"
    st = hass.states.get("number.ios2ha_camera_black_level_0")
    assert st.state == "unknown"
    assert st.attributes.get("min") == 0
