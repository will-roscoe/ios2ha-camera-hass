"""Switches. Real booleans, which is what the service's controls take."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.loader import async_get_integration

from .binary_sensor import Ios2haBinarySensor
from .bubble import BubbleModuleSwitch
from .const import DOMAIN
from .entity import Ios2haEntity, setup_platform


class Ios2haSwitch(Ios2haEntity, SwitchEntity):
    is_on = Ios2haBinarySensor.is_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.write(False)


_described = setup_platform("switch", Ios2haSwitch)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    await _described(hass, entry, async_add_entities)
    # Plus the Bubble Card module's setting, which the service knows nothing of
    # (bubble.py). Updated before it is added, so it never shows a guess.
    version = str((await async_get_integration(hass, DOMAIN)).version)
    async_add_entities([BubbleModuleSwitch(hass, entry.runtime_data, version)], True)
