from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.ios2ha_camera.api import (
    ApiDisabled,
    CannotConnect,
    NotIos2ha,
    UnsupportedApi,
)
from custom_components.ios2ha_camera.const import DOMAIN

from .conftest import load_fixture_json

PROBE = "custom_components.ios2ha_camera.config_flow.Ios2haClient.get_info"


@pytest.fixture(autouse=True)
def _no_setup():
    with patch("custom_components.ios2ha_camera.async_setup_entry", return_value=True):
        yield


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_a_reachable_service_creates_an_entry(hass):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    with patch(PROBE, AsyncMock(return_value=load_fixture_json("info"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"url": "camera-host.lan:8099/"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "iPhone Camera"
    assert result["data"] == {"url": "http://camera-host.lan:8099"}
    assert result["result"].unique_id == "ios2ha_camera"


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (CannotConnect("x"), "cannot_connect"),
        (NotIos2ha("x"), "not_ios2ha"),
        (ApiDisabled("x"), "api_disabled"),
        (UnsupportedApi(2), "unsupported_api"),
    ],
)
async def test_failures_are_named_on_the_form(hass, exc, error):
    result = await _start(hass)
    with patch(PROBE, AsyncMock(side_effect=exc)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"url": "http://camera-host.lan:8099"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_the_same_service_twice_is_refused(hass):
    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        result = await _start(hass)
        with patch(PROBE, AsyncMock(return_value=load_fixture_json("info"))):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"url": "http://camera-host.lan:8099"}
            )
        assert result["type"] is expected
