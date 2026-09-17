import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ios2ha_camera.api import Event
from custom_components.ios2ha_camera.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


INFO = load_fixture_json("info")
OBJECTS = load_fixture_json("objects")
STATE = load_fixture_json("state")

# The event every test starts from: the whole state, at the descriptor version
# the fixtures were captured at.
SNAPSHOT = Event("snapshot", {"objects_version": INFO["objects_version"], "state": STATE})


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ in every test."""
    yield


def _events_then_wait(events):
    """A stream that delivers `events` and then stays open, as a real one would."""

    async def gen():
        for e in events:
            yield e
        await asyncio.sleep(3600)

    return gen


async def _get_info(self):
    # The real get_info remembers the routes; a patch that forgot them would
    # leave the client unable to post a control.
    self.routes = dict(INFO["routes"])
    return INFO


@pytest.fixture
async def setup(hass):
    """Set up the integration against a stubbed service, then feed it `events`."""

    async def _setup(events):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"url": "http://camera-host.lan:8099"},
            unique_id="ios2ha_camera",
            title="iPhone Camera",
        )
        entry.add_to_hass(hass)
        base = "custom_components.ios2ha_camera.api.Ios2haClient"
        with (
            patch(f"{base}.get_info", _get_info),
            patch(f"{base}.get_objects", AsyncMock(return_value=OBJECTS)),
            patch(f"{base}.events", lambda self: _events_then_wait(events)()),
        ):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
        return entry

    return _setup
