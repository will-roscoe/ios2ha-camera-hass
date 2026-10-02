"""The Bubble Card module, put where Bubble Card Tools looks and kept current."""

from pathlib import Path

from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.loader import async_get_integration
import pytest
from pytest_homeassistant_custom_component.common import async_capture_events
import yaml

from custom_components.ios2ha_camera import bubble
from custom_components.ios2ha_camera.const import DOMAIN

from .conftest import SNAPSHOT


@pytest.fixture
def config_dir(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    return tmp_path


@pytest.fixture
def tools(hass):
    hass.config.components.add("bubble_card_tools")


def _on_disk(config_dir: Path) -> Path:
    return config_dir / "bubble_card" / "modules" / "ios2ha_camera.yaml"


def _version(path: Path) -> str:
    return yaml.safe_load(path.read_text())["ios2ha_camera"]["version"]


def test_the_shipped_module_is_one_bubble_module_carrying_its_code():
    data = yaml.safe_load(bubble.module_text("9.9.9"))
    assert list(data) == ["ios2ha_camera"]
    module = data["ios2ha_camera"]
    assert module["version"] == "9.9.9"
    assert "background-image" in module["code"]
    assert module["supported"] == ["button"]


async def test_install_writes_where_bubble_card_tools_reads_and_tells_it(hass, config_dir, tools):
    updated = async_capture_events(hass, "bubble_card_tools.updated")
    await bubble.async_install(hass, "0.6.0")
    await hass.async_block_till_done()
    assert _version(_on_disk(config_dir)) == "0.6.0"
    assert [(e.data["action"], e.data["name"]) for e in updated] == [
        ("write", "modules/ios2ha_camera.yaml")
    ]
    assert await bubble.async_is_installed(hass)


async def test_install_without_bubble_card_tools_says_so(hass, config_dir):
    with pytest.raises(HomeAssistantError, match="Bubble Card Tools"):
        await bubble.async_install(hass, "0.6.0")
    assert not _on_disk(config_dir).exists()


async def test_remove_deletes_the_module_and_tells_bubble_card_tools(hass, config_dir, tools):
    await bubble.async_install(hass, "0.6.0")
    updated = async_capture_events(hass, "bubble_card_tools.updated")
    await bubble.async_remove(hass)
    await hass.async_block_till_done()
    assert not _on_disk(config_dir).exists()
    assert [e.data["action"] for e in updated] == ["delete"]
    assert not await bubble.async_is_installed(hass)


async def test_removing_a_module_that_is_not_there_is_quiet(hass, config_dir, tools):
    updated = async_capture_events(hass, "bubble_card_tools.updated")
    await bubble.async_remove(hass)
    await hass.async_block_till_done()
    assert updated == []


async def test_an_update_refreshes_a_module_another_release_wrote(hass, config_dir, tools):
    await bubble.async_install(hass, "0.5.1")
    assert await bubble.async_refresh(hass, "0.6.0")
    assert _version(_on_disk(config_dir)) == "0.6.0"


async def test_a_module_this_release_wrote_is_left_alone(hass, config_dir, tools):
    # Edits made in Bubble Card's module editor last until the next release.
    await bubble.async_install(hass, "0.6.0")
    path = _on_disk(config_dir)
    path.write_text(path.read_text().replace("background-size: cover", "background-size: contain"))
    assert not await bubble.async_refresh(hass, "0.6.0")
    assert "contain" in path.read_text()


async def test_refresh_installs_nothing_that_was_not_installed(hass, config_dir, tools):
    assert not await bubble.async_refresh(hass, "0.6.0")
    assert not _on_disk(config_dir).exists()


# The setting, as a switch in the device's Configuration section.

SWITCH = "switch.ios2ha_camera_bubble_card_module"


async def _release(hass) -> str:
    return str((await async_get_integration(hass, DOMAIN)).version)


async def test_the_switch_installs_and_removes_the_module(hass, setup, config_dir, tools):
    await setup([SNAPSHOT])
    entry = er.async_get(hass).async_get(SWITCH)
    assert entry.entity_category is EntityCategory.CONFIG
    assert hass.states.get(SWITCH).state == "off"

    await hass.services.async_call("switch", "turn_on", {"entity_id": SWITCH}, blocking=True)
    assert hass.states.get(SWITCH).state == "on"
    assert _version(_on_disk(config_dir)) == await _release(hass)

    await hass.services.async_call("switch", "turn_off", {"entity_id": SWITCH}, blocking=True)
    assert hass.states.get(SWITCH).state == "off"
    assert not _on_disk(config_dir).exists()


async def test_the_switch_reads_the_disk_not_its_memory(hass, setup, config_dir, tools):
    # Every camera's switch, and Bubble Card's own editor, act on the one file.
    await setup([SNAPSHOT])
    await bubble.async_install(hass, "0.6.0")
    await async_update_entity(hass, SWITCH)
    assert hass.states.get(SWITCH).state == "on"


async def test_the_switch_works_while_the_service_is_down(hass, setup, config_dir, tools):
    # It is about Home Assistant's files, so the camera's link has no say in it.
    await setup([])
    assert hass.states.get(SWITCH).state == "off"


async def test_without_bubble_card_tools_the_switch_starts_disabled(hass, setup, config_dir):
    await setup([SNAPSHOT])
    assert er.async_get(hass).async_get(SWITCH).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_setup_brings_an_installed_module_up_to_this_release(hass, setup, config_dir, tools):
    await bubble.async_install(hass, "0.0.1")
    await setup([SNAPSHOT])
    assert _version(_on_disk(config_dir)) == await _release(hass)
