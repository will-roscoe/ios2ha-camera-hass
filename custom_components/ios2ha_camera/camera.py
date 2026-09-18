"""Cameras from the service's media descriptors.

The service describes cameras in two places and they do not line up one to one:
`still` is both a camera descriptor and a snapshot media, the `live` and
`stacked` streams are media with no camera descriptor, and `screenshot` is a
camera descriptor the service publishes only as a retained MQTT image, with no
HTTP route. Cameras are therefore the intersection-plus-media: every media entry
becomes a camera, and a camera descriptor with no media behind it is skipped
rather than given a URL the service never promised.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiohttp import ClientError, web
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_web, async_get_clientsession

from .api import Ios2haError
from .const import REQUEST_TIMEOUT
from .entity import Ios2haEntity

_LOGGER = logging.getLogger(__name__)
# A stream is meant to run until the viewer leaves, so nothing here may time it out.
_STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=REQUEST_TIMEOUT, sock_read=None)
_ICONS = {"stream": "mdi:video", "snapshot": "mdi:camera"}
# Which snapshot stands in as a stream's thumbnail. There is more than one
# snapshot now -- the camera still and the phone's screen -- and only the still
# shows what the stream shows, so picking the first in the list would put the
# phone's home screen under the live view the day the service reorders them.
_THUMBNAIL_ID = "still"


def _descriptor_for(media: dict) -> dict:
    """A descriptor for a media the service described no camera entity for.

    Derived from the media itself rather than a table of known ids, so a media
    kind added server-side arrives with a sensible name and no change here.
    """
    return {
        "object_id": media["id"],
        "domain": "camera",
        "name": media["id"].replace("_", " ").capitalize(),
        "state_key": None,
        "icon": _ICONS.get(media.get("kind")),
        "category": None,
    }


class Ios2haCamera(Ios2haEntity, Camera):
    # Not STREAM: that advertises HLS or WebRTC, which the service does not offer.
    _attr_supported_features = CameraEntityFeature(0)

    def __init__(self, coordinator, descriptor, media: dict, still: dict | None) -> None:
        Ios2haEntity.__init__(self, coordinator, descriptor)
        Camera.__init__(self)
        self.media = media
        self.still = still

    @property
    def available(self) -> bool:
        return self.coordinator.connected

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        # A thumbnail must never hold the phone, so a stream's still comes from
        # the snapshot route rather than a frame off the stream itself.
        source = self.media if self.media["kind"] == "snapshot" else self.still
        if source is None:
            return None
        try:
            url = self.coordinator.client.url(source["url"])
        except Ios2haError:
            # A media path that does not belong to the configured service. The
            # client has already refused it; no image is the right answer.
            _LOGGER.warning("refusing media path %r", source.get("url"))
            return None
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await session.get(url)
                resp.raise_for_status()
                return await resp.read()
        except ClientError, TimeoutError:
            return None

    async def handle_async_mjpeg_stream(self, request: web.Request) -> web.StreamResponse | None:
        if self.media["kind"] != "stream" or "mjpeg" not in self.media.get("formats", []):
            return None
        try:
            url = self.coordinator.client.url(self.media["url"])
        except Ios2haError:
            _LOGGER.warning("refusing stream path %r", self.media.get("url"))
            return None
        session = async_get_clientsession(self.hass)
        # Holds the phone for as long as the viewer stays; the service lets go
        # after its linger once the viewer leaves.
        stream = session.get(url, timeout=_STREAM_TIMEOUT)
        return await async_aiohttp_proxy_web(self.hass, request, stream)


def _thumbnail_source(media: list[dict]) -> dict | None:
    """The snapshot a stream should use for its thumbnail, or None if there is
    no snapshot at all: a stream must never be its own thumbnail, or drawing a
    dashboard would hold the phone."""
    snapshots = [m for m in media if m.get("kind") == "snapshot" and not m.get("holds_phone")]
    by_id = {m["id"]: m for m in snapshots}
    return by_id.get(_THUMBNAIL_ID) or (snapshots[0] if snapshots else None)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    described = {d["object_id"]: d for d in coordinator.descriptors("camera")}
    still = _thumbnail_source(coordinator.media)
    async_add_entities(
        Ios2haCamera(coordinator, described.get(m["id"]) or _descriptor_for(m), m, still)
        for m in coordinator.media
    )
