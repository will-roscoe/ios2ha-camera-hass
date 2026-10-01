"""Attributes and actions: the two things the service's shared layer gained in 2.16.0.

Both are read from the descriptors, so nothing here knows what a timelapse is.
"""

from custom_components.ios2ha_camera.coordinator import Ios2haCoordinator

from .conftest import OBJECTS, SNAPSHOT


async def test_a_sensor_carries_the_state_its_descriptor_names_as_attributes(hass, setup):
    await setup([SNAPSHOT])
    state = hass.states.get("sensor.ios2ha_camera_timelapses")
    assert state.state == "1"
    entry = state.attributes["items"]["last_24h"]
    assert entry["url"] == "/api/v1/timelapse/last_24h.mp4" and entry["frames"] == 141


async def test_a_sensor_without_one_has_no_extra_attributes(hass, setup):
    await setup([SNAPSHOT])
    assert "items" not in hass.states.get("sensor.ios2ha_camera_battery").attributes


async def test_the_coordinator_keeps_the_actions(hass, setup):
    entry = await setup([SNAPSHOT])
    coordinator: Ios2haCoordinator = entry.runtime_data
    assert [a["name"] for a in coordinator.actions] == ["build_timelapse", "delete_timelapse"]
    assert coordinator.actions == OBJECTS["actions"]


async def test_a_service_from_before_actions_gives_none(hass):
    coordinator = Ios2haCoordinator.__new__(Ios2haCoordinator)
    coordinator._use({"objects": [], "media": []})
    assert coordinator.actions == []


async def test_the_reason_for_an_outcome_is_an_attribute(hass, setup):
    await setup([SNAPSHOT])
    state = hass.states.get("sensor.ios2ha_camera_timelapse")
    assert state.state == "built" and state.attributes["result"] == "built"


async def test_attributes_from_the_service_are_not_recorded(hass, setup):
    """A catalogue can grow past the recorder's 16 KiB, and its history is of no use."""
    from homeassistant.const import MATCH_ALL

    await setup([SNAPSHOT])
    entity = hass.data["entity_components"]["sensor"].get_entity("sensor.ios2ha_camera_timelapses")
    assert MATCH_ALL in entity._unrecorded_attributes
    battery = hass.data["entity_components"]["sensor"].get_entity("sensor.ios2ha_camera_battery")
    assert MATCH_ALL not in battery._unrecorded_attributes


async def test_every_entity_says_which_object_it_is(hass, setup):
    """Entity ids can change -- a rename, or `_2` for a second camera -- so the card
    finds an entity by its translation key, which is the service's object id."""
    from homeassistant.helpers import entity_registry as er

    await setup([SNAPSHOT])
    reg = er.async_get(hass)
    assert reg.async_get("sensor.ios2ha_camera_timelapses").translation_key == "timelapses"
    assert reg.async_get("camera.ios2ha_camera_still").translation_key == "still"
    assert reg.async_get("number.ios2ha_camera_interval_s").translation_key == "interval_s"
    # a translation key must not take over the names the service gives
    assert (
        hass.states.get("sensor.ios2ha_camera_timelapses")
        .attributes["friendly_name"]
        .endswith("Timelapses")
    )
