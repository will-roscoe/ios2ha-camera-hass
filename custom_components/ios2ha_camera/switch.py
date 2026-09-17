"""Switches. Real booleans, which is what the service's controls take."""

from homeassistant.components.switch import SwitchEntity

from .binary_sensor import Ios2haBinarySensor
from .entity import Ios2haEntity, setup_platform


class Ios2haSwitch(Ios2haEntity, SwitchEntity):
    is_on = Ios2haBinarySensor.is_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.write(False)


async_setup_entry = setup_platform("switch", Ios2haSwitch)
