"""The service's video media in Home Assistant's Media panel.

A `video` media descriptor (service 2.16.0: the timelapses) names the state key that
lists its items -- `{"items": {name: {..., "url": ...}}}` -- each with the url it is
served at. Browsing lists them per camera;
playing one resolves to this integration's view (views.py), a relative path that
Home Assistant signs, so it plays wherever Home Assistant can be reached.
"""

from __future__ import annotations

from homeassistant.components.media_player import MediaClass
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import DOMAIN

MIME = {"mp4": "video/mp4"}


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return Ios2haMediaSource(hass)


def media_url(entry_id: str, media_id: str, name: str) -> str:
    """This integration's path for one item, which views.py serves."""
    return f"/api/{DOMAIN}/{entry_id}/media/{media_id}/{name}.mp4"


def listed(coordinator, media_id: str) -> tuple[dict | None, dict]:
    """A video media descriptor with a catalogue, and the items it lists now."""
    media = next(
        (
            m
            for m in coordinator.media
            if m.get("id") == media_id and m.get("kind") == "video" and m.get("catalogue")
        ),
        None,
    )
    catalogue = coordinator.data.get(media["catalogue"]) if media else None
    items = catalogue.get("items") if isinstance(catalogue, dict) else None
    return media, items if isinstance(items, dict) else {}


def _title(name: str, item: dict) -> str:
    parts = [
        f"{item['frames']} frames" if "frames" in item else None,
        f"{item['duration_s']} s" if "duration_s" in item else None,
    ]
    detail = ", ".join(p for p in parts if p)
    return f"{name} ({detail})" if detail else name


class Ios2haMediaSource(MediaSource):
    name = "iPhone Camera"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def _entries(self):
        return [
            e
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]

    def _entry(self, entry_id: str):
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise Unresolvable(f"no camera {entry_id}")
        return entry

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        parts = (item.identifier or "").split("/")
        if len(parts) != 3:
            raise Unresolvable(f"not a playable item: {item.identifier}")
        entry_id, media_id, name = parts
        media, items = listed(self._entry(entry_id).runtime_data, media_id)
        if media is None or name not in items:
            raise Unresolvable(f"{name} is not listed")
        mime = MIME.get((media.get("formats") or ["mp4"])[0], "video/mp4")
        return PlayMedia(media_url(entry_id, media_id, name), mime)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        parts = [p for p in (item.identifier or "").split("/") if p]
        if not parts:
            return self._folder(
                None,
                self.name,
                [self._folder(e.entry_id, e.title, [], leaf=False) for e in self._entries()],
            )
        entry = self._entry(parts[0])
        coordinator = entry.runtime_data
        if len(parts) == 1:
            return self._folder(
                entry.entry_id,
                entry.title,
                [
                    self._folder(
                        f"{entry.entry_id}/{m['id']}", f"{m['id'].capitalize()}s", [], leaf=False
                    )
                    for m in coordinator.media
                    if m.get("kind") == "video" and m.get("catalogue")
                ],
            )
        media, items = listed(coordinator, parts[1])
        if media is None:
            raise Unresolvable(f"no media {parts[1]}")
        newest = sorted(items.items(), key=lambda kv: str(kv[1].get("built", "")), reverse=True)
        return self._folder(
            f"{entry.entry_id}/{parts[1]}",
            f"{parts[1].capitalize()}s",
            [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry.entry_id}/{parts[1]}/{name}",
                    media_class=MediaClass.VIDEO,
                    media_content_type="video/mp4",
                    title=_title(name, it),
                    can_play=True,
                    can_expand=False,
                )
                for name, it in newest
            ],
        )

    def _folder(self, identifier, title, children, leaf=True) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children=children if leaf else None,
            children_media_class=MediaClass.VIDEO if leaf else MediaClass.DIRECTORY,
        )
