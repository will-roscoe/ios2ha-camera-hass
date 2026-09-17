"""Buttons. A press carries no value at all."""

from homeassistant.components.button import ButtonEntity

from .api import NO_VALUE
from .entity import Ios2haEntity, setup_platform


class Ios2haButton(Ios2haEntity, ButtonEntity):
    async def async_press(self) -> None:
        # Presses of phone-working buttons are coalesced by the service: a repeat
        # press while one is running is answered 200 and not run twice.
        await self.write(NO_VALUE)


async_setup_entry = setup_platform("button", Ios2haButton)
