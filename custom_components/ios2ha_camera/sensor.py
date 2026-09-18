"""Sensors, entirely from descriptors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.util import dt as dt_util

from .entity import Ios2haEntity, setup_platform


def _date(text):
    parsed = dt_util.parse_datetime(text)
    return parsed.date() if parsed else dt_util.parse_date(text)


# Unparseable text becomes None, which shows as unknown rather than raising: bad
# input from the service should not take the entity down.
_PARSED = {
    SensorDeviceClass.TIMESTAMP: dt_util.parse_datetime,
    SensorDeviceClass.DATE: _date,
}


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
        value = self.value
        # JSON has no datetime, so the service sends ISO 8601 text. Home
        # Assistant rejects a string outright for these two device classes and
        # leaves the entity with no state, so the parsing has to happen here.
        if isinstance(value, str) and self._attr_device_class in _PARSED:
            return _PARSED[self._attr_device_class](value)
        return value


async_setup_entry = setup_platform("sensor", Ios2haSensor)
