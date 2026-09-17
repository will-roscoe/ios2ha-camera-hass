"""One event stream feeding every entity."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import CannotConnect, Ios2haClient, Ios2haError
from .const import DOMAIN, RECONNECT_MAX, RECONNECT_MIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


def _backoff(attempt: int) -> float:
    return min(RECONNECT_MAX, RECONNECT_MIN * 2**attempt)


class Ios2haCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the flat state, the entity descriptors, and the stream that feeds them."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: Ios2haClient) -> None:
        # No update_interval: nothing polls, the event stream pushes.
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.entry = entry
        self.client = client
        self.info: dict = {}
        self.objects: list[dict] = []
        self.media: list[dict] = []
        self.objects_version: str | None = None
        self.connected = False
        self.data = {}
        self.reconnect_delay = _backoff
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._task: asyncio.Task | None = None

    def descriptors(self, domain: str) -> list[dict]:
        return [d for d in self.objects if d.get("domain") == domain]

    async def async_prepare(self) -> None:
        """Get enough to build entities: from the service, or from the cache."""
        cached = await self._store.async_load()
        try:
            self.info = await self.client.get_info()
        except CannotConnect as err:
            # Entities the service described before are worth showing as
            # unavailable; with no cache there is nothing to show at all.
            if not cached:
                raise ConfigEntryNotReady(str(err)) from err
            self.info = cached.get("info", {})
            self._use(cached["objects"])
            return
        if cached and cached.get("objects_version") == self.info.get("objects_version"):
            self._use(cached["objects"])
        else:
            await self._refresh_objects()

    def _use(self, doc: dict) -> None:
        self.objects = list(doc.get("objects", []))
        self.media = list(doc.get("media", []))
        self.objects_version = doc.get("objects_version")

    async def _refresh_objects(self) -> None:
        doc = await self.client.get_objects()
        self._use(doc)
        await self._store.async_save(
            {"objects_version": self.objects_version, "objects": doc, "info": self.info}
        )

    def start(self) -> None:
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), f"{DOMAIN} event stream"
        )

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                if not self.client.routes:
                    self.info = await self.client.get_info()
                async for event in self.client.events():
                    attempt = 0
                    await self._handle(event)
                reason = "closed by the service"
            except Ios2haError as err:
                reason = str(err)
            if self.connected:
                _LOGGER.info("event stream lost (%s); reconnecting", reason)
            self.connected = False
            self.async_update_listeners()
            await asyncio.sleep(self.reconnect_delay(attempt))
            attempt += 1

    async def _handle(self, event) -> None:
        if event.name == "snapshot":
            # A snapshot is the whole state: a reconnect replaces, never merges.
            state = event.data.get("state")
            if not isinstance(state, dict):
                return
            self.connected = True
            if event.data.get("objects_version") != self.objects_version:
                await self._objects_changed()
            self.async_set_updated_data(dict(state))
        elif event.name == "state":
            state = event.data.get("state")
            if isinstance(state, dict) and self.connected:
                self.async_set_updated_data({**self.data, **state})
        elif event.name == "objects_changed":
            await self._objects_changed()
        # Any other event name is from a newer service; ignore it.

    async def _objects_changed(self) -> None:
        await self._refresh_objects()
        _LOGGER.info("entity descriptors changed; reloading")
        self.hass.config_entries.async_schedule_reload(self.entry.entry_id)
