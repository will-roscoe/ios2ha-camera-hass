"""Numbers, with their limits taken from the descriptor."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode

from .entity import Ios2haEntity, setup_platform
from .sensor import _enum


class Ios2haNumber(Ios2haEntity, NumberEntity):
    # The MQTT discovery payload says "box"; a slider here would be a second
    # answer to a question the service has already answered.
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, descriptor):
        super().__init__(coordinator, descriptor)
        self._attr_native_min_value = descriptor["lo"]
        self._attr_native_max_value = descriptor["hi"]
        self._attr_native_step = descriptor["step"]
        self._attr_native_unit_of_measurement = descriptor.get("unit")
        self._attr_device_class = _enum(NumberDeviceClass, descriptor.get("device_class"))

    @property
    def native_value(self):
        return self.value

    async def async_set_native_value(self, value: float) -> None:
        # Home Assistant hands every number over as a float; a control whose
        # step is whole numbers should not receive 900.0 where it expects 900.
        await self.write(int(value) if float(value).is_integer() else value)


async_setup_entry = setup_platform("number", Ios2haNumber)
