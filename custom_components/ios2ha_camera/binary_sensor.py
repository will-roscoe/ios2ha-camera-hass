"""Binary sensors, entirely from descriptors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import Ios2haEntity, setup_platform
from .sensor import _enum


class Ios2haBinarySensor(Ios2haEntity, BinarySensorEntity):
    def __init__(self, coordinator, descriptor):
        super().__init__(coordinator, descriptor)
        self._attr_device_class = _enum(BinarySensorDeviceClass, descriptor.get("device_class"))

    @property
    def is_on(self):
        v = self.value
        if isinstance(v, str):
            return v.lower() in ("on", "true", "1")
        return None if v is None else bool(v)


async_setup_entry = setup_platform("binary_sensor", Ios2haBinarySensor)
