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
