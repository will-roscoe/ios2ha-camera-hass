"""Entities built from the service's own descriptors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, OBJECT_ID_PREFIX
from .coordinator import Ios2haCoordinator

_CATEGORY = {"config": EntityCategory.CONFIG, "diagnostic": EntityCategory.DIAGNOSTIC}


def device_info(coordinator: Ios2haCoordinator) -> DeviceInfo:
    dev = coordinator.info.get("device", {})
    return DeviceInfo(
        identifiers={(DOMAIN, i) for i in dev.get("identifiers", [OBJECT_ID_PREFIX])},
        name=dev.get("name"),
        manufacturer=dev.get("manufacturer"),
        model=dev.get("model"),
        sw_version=dev.get("sw_version"),
        configuration_url=coordinator.client.base_url,
    )


class Ios2haEntity(CoordinatorEntity[Ios2haCoordinator]):
    """Whatever the descriptor says it is. Nothing here is per-entity knowledge."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Ios2haCoordinator, descriptor: dict) -> None:
        super().__init__(coordinator)
        self.descriptor = descriptor
        domain, object_id = descriptor["domain"], descriptor["object_id"]
        self.state_key: str | None = descriptor.get("state_key")
        # Pinned to the id MQTT discovery used, so automations survive migration.
        self.entity_id = f"{domain}.{OBJECT_ID_PREFIX}_{object_id}"
        self._attr_unique_id = f"{coordinator.entry.unique_id}-{domain}-{object_id}"
        self._attr_name = descriptor.get("name")
        self._attr_icon = descriptor.get("icon")
        self._attr_entity_category = _CATEGORY.get(descriptor.get("category"))
        self._attr_device_info = device_info(coordinator)

    @property
    def value(self) -> Any:
        return self.coordinator.data.get(self.state_key) if self.state_key else None

    @property
    def available(self) -> bool:
        if not self.coordinator.connected:
            return False
        return self.state_key is None or self.state_key in self.coordinator.data


def setup_platform(domain: str, factory: Callable[[Ios2haCoordinator, dict], Entity]):
    """Build every entity of one domain from the descriptors, and nothing else."""

    async def async_setup_entry(
        hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
    ) -> None:
        coordinator: Ios2haCoordinator = entry.runtime_data
        async_add_entities(factory(coordinator, d) for d in coordinator.descriptors(domain))

    return async_setup_entry
