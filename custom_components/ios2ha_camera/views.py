"""Serve the service's video media through Home Assistant.

The media source resolves an item to this view's path; Home Assistant signs it, so
a browser anywhere Home Assistant is reachable can play it, and the service itself
stays on the LAN. Range is passed through, so players can seek.
"""

from __future__ import annotations

import logging
import re

from aiohttp import ClientError, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NotIos2ha
from .const import DOMAIN
from .media_source import listed

_LOGGER = logging.getLogger(__name__)

_NAME = re.compile(r"\A[a-z0-9_-]{1,48}\Z")  # not $: it also matches before a newline
_PASSED_BACK = (
    "Content-Type",
    "Content-Length",
    "Content-Range",
    "Accept-Ranges",
    "Last-Modified",
    "ETag",
)
_CHUNK = 64 * 1024


class Ios2haMediaView(HomeAssistantView):
    url = f"/api/{DOMAIN}/{{entry_id}}/media/{{media_id}}/{{name}}.mp4"
    name = f"api:{DOMAIN}:media"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(
        self, request: web.Request, entry_id: str, media_id: str, name: str
    ) -> web.StreamResponse:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or not _NAME.match(name)
        ):
            raise web.HTTPNotFound
        coordinator = entry.runtime_data
        _, items = listed(coordinator, media_id)
        item = items.get(name)
        if not isinstance(item, dict) or not item.get("url"):
            raise web.HTTPNotFound
        try:
            # The catalogue is network input: a url that leaves the service is
            # refused before any request is made (api.Ios2haClient.url).
            upstream = coordinator.client.url(item["url"])
        except NotIos2ha as err:
            _LOGGER.warning("refused %s: %s", name, err)
            raise web.HTTPNotFound from err
        headers = {"Range": request.headers["Range"]} if "Range" in request.headers else {}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(upstream, headers=headers) as up:
                if up.status >= 400:
                    raise web.HTTPNotFound if up.status == 404 else web.HTTPBadGateway
                response = web.StreamResponse(
                    status=up.status,
                    headers={k: up.headers[k] for k in _PASSED_BACK if k in up.headers},
                )
                await response.prepare(request)
                try:
                    async for chunk in up.content.iter_chunked(_CHUNK):
                        await response.write(chunk)
                    await response.write_eof()
                except ConnectionResetError:
                    # The viewer went: a video element drops a request on every
                    # seek. Nothing is wrong, and nothing is left to send.
                    _LOGGER.debug("viewer of %s went mid-stream", name)
                return response
        except ClientError as err:
            raise web.HTTPBadGateway(text=f"the camera's service did not answer: {err}") from err
