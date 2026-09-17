from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from .conftest import SNAPSHOT


async def test_diagnostics_summarise_without_the_address(hass, hass_client, setup):
    assert await async_setup_component(hass, "diagnostics", {})
    entry = await setup([SNAPSHOT])
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diag["connected"] is True
    assert diag["entry"]["url"] == "**REDACTED**"
    assert diag["domains"]["sensor"] > 0
    assert "camera-host.lan" not in str(diag)
