import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from custom_components.ios2ha_camera.api import Event, Ios2haClient

from .conftest import load_fixture_json

# A real server over a loopback socket, which the Home Assistant test plugin
# blocks unless a test asks for it.
pytestmark = pytest.mark.usefixtures("socket_enabled")

STREAM = (
    b": keepalive\n\n"
    b'event: snapshot\ndata: {"objects_version": "sha256:a", "state": {"x": 1}}\n\n'
    b'event: future_thing\ndata: {"y": 2}\n\n'
    b"event: state\ndata: not json\n\n"
    b'event: state\ndata: {"state": {"x": 2}}\n\n'
)


async def _server(chunks):
    async def events(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        for c in chunks:
            await resp.write(c)
        return resp

    async def info(request):
        return web.json_response(load_fixture_json("info"))

    app = web.Application()
    app.router.add_get("/api/v1/info", info)
    app.router.add_get("/api/v1/events", events)
    server = TestServer(app)
    await server.start_server()
    return server


async def _collect(chunks):
    server = await _server(chunks)
    async with aiohttp.ClientSession() as s:
        c = Ios2haClient(s, str(server.make_url("/")))
        await c.get_info()
        got = [e async for e in c.events()]
    await server.close()
    return got


async def test_events_are_parsed_and_unknown_names_passed_through():
    got = await _collect([STREAM])
    assert got == [
        Event("snapshot", {"objects_version": "sha256:a", "state": {"x": 1}}),
        Event("future_thing", {"y": 2}),
        Event("state", {"state": {"x": 2}}),
    ]


async def test_a_block_split_across_network_chunks_is_reassembled():
    raw = b'event: state\ndata: {"state": {"x": 3}}\n\n'
    got = await _collect([raw[:9], raw[9:20], raw[20:]])
    assert got == [Event("state", {"state": {"x": 3}})]


async def test_crlf_line_endings_are_accepted():
    got = await _collect([b'event: state\r\ndata: {"state": {}}\r\n\r\n'])
    assert got == [Event("state", {"state": {}})]
