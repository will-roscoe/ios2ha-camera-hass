"""Sensors, entirely from descriptors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass

from .entity import Ios2haEntity, setup_platform


def _enum(cls, value):
    try:
        return cls(value) if value else None
    except ValueError:  # a device class this Home Assistant does not know
        return None


class Ios2haSensor(Ios2haEntity, SensorEntity):
    def __init__(self, coordinator, descriptor):
        super().__init__(coordinator, descriptor)
        self._attr_device_class = _enum(SensorDeviceClass, descriptor.get("device_class"))
        self._attr_state_class = _enum(SensorStateClass, descriptor.get("state_class"))
        self._attr_native_unit_of_measurement = descriptor.get("unit")
        self._attr_suggested_display_precision = descriptor.get("precision")
        if descriptor.get("options") is not None:
            self._attr_options = list(descriptor["options"])

    @property
    def native_value(self):
        return self.value


async_setup_entry = setup_platform("sensor", Ios2haSensor)
