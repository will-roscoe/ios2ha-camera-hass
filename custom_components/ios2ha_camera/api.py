"""A small client for the ios2ha-camera JSON API (/api/v1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
from typing import Any

import aiohttp
from yarl import URL

from .const import INFO_PATH, REQUEST_TIMEOUT, SUPPORTED_API

NO_VALUE = object()


class Ios2haError(Exception):
    """Base for everything this client raises."""


class CannotConnect(Ios2haError):
    """Nothing usable answered at the address."""


class NotIos2ha(Ios2haError):
    """Something answered, but not an ios2ha-camera service."""


class ApiDisabled(Ios2haError):
    """The service answered but its JSON API is off (EXPOSE_API=false)."""


class UnsupportedApi(Ios2haError):
    """The service speaks an API major version this integration does not."""

    def __init__(self, found: object) -> None:
        super().__init__(f"unsupported API version {found!r}")
        self.found = found


class ControlRejected(Ios2haError):
    """The service refused a control write."""

    def __init__(self, status: int, error: str) -> None:
        super().__init__(f"{status}: {error}")
        self.status = status
        self.error = error


@dataclass(frozen=True)
class Event:
    """One server-sent event: its name and its decoded JSON object."""

    name: str
    data: dict


# No total timeout: the stream is meant to stay open. The service sends a
# keepalive comment every ~20 s, so a read that quiet for 90 s is a dead link.
_STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=REQUEST_TIMEOUT, sock_read=90)


def _parse_block(lines: list[str]) -> Event | None:
    name, data = "message", []
    for line in lines:
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            name = value
        elif field == "data":
            data.append(value)
    if not data:
        return None
    try:
        payload = json.loads("\n".join(data))
    except ValueError:
        return None
    return Event(name, payload) if isinstance(payload, dict) else None


class Ios2haClient:
    """Speaks the four JSON routes. Only /info's path is hardcoded."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self.routes: dict[str, str] = {}

    def url(self, path: str) -> str:
        """Absolute URL for a path the service named.

        Every path but `/info` comes out of `/info`'s routes map or a media
        descriptor, so these strings are network input rather than constants,
        and the link carries neither TLS nor authentication by design. Joining
        them by concatenation would let anything able to answer as the service
        move the request to a host of its choosing: `"@evil.example/x"` glued to
        `http://camera-host.lan:8099` parses as userinfo `camera-host.lan:8099`
        at host `evil.example`, which would hand it Home Assistant's network
        position and render whatever it returned as a camera.

        So a path must be one this base can actually address: rooted, not
        protocol-relative, and resolving to the same origin.
        """
        if not path.startswith("/") or path.startswith("//"):
            raise NotIos2ha(f"not a rooted path: {path!r}")
        base = URL(self.base_url)
        resolved = base.join(URL(path))
        if resolved.origin() != base.origin():
            raise NotIos2ha(f"path leaves {base.origin()}: {path!r}")
        return str(resolved)

    async def _get_json(self, path: str) -> Any:
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.get(self.url(path)) as resp,
            ):
                if resp.status == 404:
                    raise ApiDisabled(path)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except Ios2haError:
            raise
        except ValueError as err:  # body was not JSON
            raise NotIos2ha(str(err)) from err
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise CannotConnect(str(err)) from err

    async def get_info(self) -> dict:
        info = await self._get_json(INFO_PATH)
        try:
            api = info["interfaces"]["api"]
            routes = info["routes"]
            info["device"]["identifiers"]
        except (KeyError, TypeError) as err:
            raise NotIos2ha("unexpected /info shape") from err
        if api != SUPPORTED_API:
            raise UnsupportedApi(api)
        self.routes = dict(routes)
        return info

    async def get_objects(self) -> dict:
        return await self._get_json(self.routes["objects"])

    async def get_state(self) -> dict:
        return await self._get_json(self.routes["state"])

    async def post_control(self, name: str, value: object = NO_VALUE) -> dict:
        path = self.routes["control"].replace("{name}", name)
        # A button carries no value at all, which is not the same as a null one.
        body = b"" if value is NO_VALUE else json.dumps({"value": value}).encode()
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.post(
                    self.url(path), data=body, headers={"Content-Type": "application/json"}
                ) as resp,
            ):
                status = resp.status
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as err:
            raise CannotConnect(str(err)) from err
        if status >= 400:
            raise ControlRejected(status, str(data.get("error", "")))
        return data

    async def events(self) -> AsyncIterator[Event]:
        """Yield events until the service closes the stream or the link dies."""
        try:
            resp = await self._session.get(
                self.url(self.routes["events"]),
                timeout=_STREAM_TIMEOUT,
                headers={"Accept": "text/event-stream"},
            )
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise CannotConnect(str(err)) from err
        async with resp:
            if resp.status == 404:
                raise ApiDisabled(self.routes["events"])
            if resp.status != 200:
                raise CannotConnect(f"events: HTTP {resp.status}")
            lines: list[str] = []
            try:
                async for raw in resp.content:  # aiohttp yields whole lines
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if line:
                        lines.append(line)
                        continue
                    event = _parse_block(lines)
                    lines = []
                    if event is not None:
                        yield event
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                raise CannotConnect(str(err)) from err
