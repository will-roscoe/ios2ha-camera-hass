"""Selects, with their options taken from the descriptor."""

from homeassistant.components.select import SelectEntity

from .entity import Ios2haEntity, setup_platform


class Ios2haSelect(Ios2haEntity, SelectEntity):
    def __init__(self, coordinator, descriptor):
        super().__init__(coordinator, descriptor)
        self._attr_options = list(descriptor["options"])

    @property
    def current_option(self):
        return self.value

    async def async_select_option(self, option: str) -> None:
        await self.write(option)


async_setup_entry = setup_platform("select", Ios2haSelect)
