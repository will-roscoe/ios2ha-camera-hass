from unittest.mock import AsyncMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.ios2ha_camera.api import NO_VALUE, ControlRejected

from .conftest import SNAPSHOT

POST = "custom_components.ios2ha_camera.api.Ios2haClient.post_control"


@pytest.mark.parametrize(
    ("service", "entity_id", "data", "expected"),
    [
        (
            ("number", "set_value"),
            "number.ios2ha_camera_interval_s",
            {"value": 900},
            ("interval_s", 900),
        ),
        (
            ("select", "select_option"),
            "select.ios2ha_camera_stacking_mode",
            {"option": "auto"},
            ("stacking_mode", "auto"),
        ),
        (
            ("switch", "turn_on"),
            "switch.ios2ha_camera_stacking_allowed",
            {},
            ("stacking_allowed", True),
        ),
        (
            ("switch", "turn_off"),
            "switch.ios2ha_camera_stacking_allowed",
            {},
            ("stacking_allowed", False),
        ),
        (
            ("button", "press"),
            "button.ios2ha_camera_capture_now",
            {},
            ("capture_now", NO_VALUE),
        ),
    ],
)
async def test_each_control_posts_one_write(hass, setup, service, entity_id, data, expected):
    await setup([SNAPSHOT])
    with patch(POST, AsyncMock(return_value={"ok": True})) as post:
        await hass.services.async_call(*service, {"entity_id": entity_id, **data}, blocking=True)
    post.assert_awaited_once_with(*expected)


async def test_a_refused_write_surfaces_the_server_reason(hass, setup):
    await setup([SNAPSHOT])
    with (
        patch(POST, AsyncMock(side_effect=ControlRejected(400, "out of range"))),
        pytest.raises(HomeAssistantError, match="out of range"),
    ):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.ios2ha_camera_interval_s", "value": 30},
            blocking=True,
        )


async def test_number_limits_come_from_the_descriptor(hass, setup):
    await setup([SNAPSHOT])
    st = hass.states.get("number.ios2ha_camera_interval_s")
    assert (st.attributes["min"], st.attributes["max"], st.attributes["step"]) == (30, 3600, 1)


async def test_screenshot_exists_as_a_button(hass, setup):
    await setup([SNAPSHOT])
    assert hass.states.get("button.ios2ha_camera_screenshot") is not None
