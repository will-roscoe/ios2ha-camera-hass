"""A small client for the ios2ha-camera JSON API (/api/v1)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

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


class Ios2haClient:
    """Speaks the four JSON routes. Only /info's path is hardcoded."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self.routes: dict[str, str] = {}

    def url(self, path: str) -> str:
        return self.base_url + path

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
