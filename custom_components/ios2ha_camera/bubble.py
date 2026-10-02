"""The Bubble Card module, installed where Bubble Card Tools keeps modules.

Bubble Card Tools, a separate integration, reads Bubble Card's modules from
/config/bubble_card/modules/, and refreshes its editor when its
`bubble_card_tools.updated` event says one has changed: the same two things its own
editor does on a save. The copy is stamped with this integration's version, so an
update can tell an older release's copy from its own, and leaves edits made in
Bubble Card's module editor alone until the next release.
"""

from __future__ import annotations

from pathlib import Path
import re

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import yaml

from .const import OBJECT_ID_PREFIX
from .coordinator import Ios2haCoordinator
from .entity import device_info

TOOLS = "bubble_card_tools"
MODULE = "modules/ios2ha_camera.yaml"  # as Bubble Card Tools names it
_SHIPPED = Path(__file__).parent / "modules" / "ios2ha_camera.yaml"
_VERSION = re.compile(r"^(  version: ).*$", re.MULTILINE)


def module_text(version: str) -> str:
    """The shipped module, stamped with `version`."""
    text = _SHIPPED.read_text(encoding="utf-8")
    return _VERSION.sub(lambda m: f'{m[1]}"{version}"', text, count=1)


def tools_loaded(hass: HomeAssistant) -> bool:
    return TOOLS in hass.config.components


async def async_is_installed(hass: HomeAssistant) -> bool:
    return await hass.async_add_executor_job(_path(hass).exists)


async def async_install(hass: HomeAssistant, version: str) -> None:
    if not tools_loaded(hass):
        raise HomeAssistantError(
            "Bubble Card Tools is not installed, so Bubble Card has nowhere to read the module from"
        )
    await hass.async_add_executor_job(_write, _path(hass), version)
    _updated(hass, "write")


async def async_remove(hass: HomeAssistant) -> None:
    if await hass.async_add_executor_job(_unlink, _path(hass)):
        _updated(hass, "delete")


async def async_refresh(hass: HomeAssistant, version: str) -> bool:
    """Bring an installed copy up to this release; True if it was rewritten."""
    if await hass.async_add_executor_job(_refresh, _path(hass), version):
        _updated(hass, "write")
        return True
    return False


class BubbleModuleSwitch(SwitchEntity):
    """The setting, in the device's Configuration section.

    The one entity the service does not describe: it is about Home Assistant's own
    files, so neither MQTT nor the service's page has anything to do with it. Its
    state is the file on disk, read again on each poll, so a second camera's switch
    and Bubble Card's own editor, which act on the same file, never disagree with it.
    It starts disabled where Bubble Card Tools is not installed.
    """

    _attr_has_entity_name = True
    _attr_name = "Bubble Card module"
    _attr_translation_key = "bubble_card_module"
    _attr_icon = "mdi:card-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, coordinator: Ios2haCoordinator, version: str) -> None:
        self._version = version
        self.entity_id = f"switch.{OBJECT_ID_PREFIX}_bubble_card_module"
        self._attr_unique_id = f"{coordinator.entry.unique_id}-switch-bubble_card_module"
        self._attr_device_info = device_info(coordinator)
        self._attr_entity_registry_enabled_default = tools_loaded(hass)

    async def async_update(self) -> None:
        self._attr_is_on = await async_is_installed(self.hass)

    async def async_turn_on(self, **kwargs) -> None:
        await async_install(self.hass, self._version)

    async def async_turn_off(self, **kwargs) -> None:
        await async_remove(self.hass)


def _path(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("bubble_card", MODULE))


def _write(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(module_text(version), encoding="utf-8")


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _refresh(path: Path, version: str) -> bool:
    if not path.exists():
        return False
    try:
        installed = yaml.safe_load(path.read_text(encoding="utf-8"))["ios2ha_camera"]["version"]
    except OSError, yaml.YAMLError, KeyError, TypeError:
        installed = None  # unreadable: the copy is the integration's, so it is replaced
    if installed == version:
        return False
    _write(path, version)
    return True


def _updated(hass: HomeAssistant, action: str) -> None:
    ts = dt_util.utcnow().isoformat().replace("+00:00", "Z")
    hass.bus.async_fire(f"{TOOLS}.updated", {"action": action, "name": MODULE, "ts": ts})
