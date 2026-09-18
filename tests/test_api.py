import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from custom_components.ios2ha_camera.api import (
    NO_VALUE,
    ApiDisabled,
    CannotConnect,
    ControlRejected,
    Ios2haClient,
    NotIos2ha,
    UnsupportedApi,
)

from .conftest import load_fixture_json

# These tests drive a real aiohttp server over a loopback socket, which the
# Home Assistant test plugin blocks unless a test asks for it.
pytestmark = pytest.mark.usefixtures("socket_enabled")


async def _serve(routes):
    app = web.Application()
    for method, path, handler in routes:
        app.router.add_route(method, path, handler)
    server = TestServer(app)
    await server.start_server()
    return server


def _json(data, status=200):
    async def handler(request):
        return web.json_response(data, status=status)

    return handler


async def test_info_is_read_and_routes_remembered():
    info = load_fixture_json("info")
    server = await _serve([("GET", "/api/v1/info", _json(info))])
    async with aiohttp.ClientSession() as s:
        c = Ios2haClient(s, str(server.make_url("/")))
        got = await c.get_info()
    await server.close()
    assert got["device"]["identifiers"] == ["ios2ha_camera"]
    assert c.routes["events"] == "/api/v1/events"


async def test_unknown_info_keys_are_ignored():
    info = load_fixture_json("info") | {"something_new": {"x": 1}}
    server = await _serve([("GET", "/api/v1/info", _json(info))])
    async with aiohttp.ClientSession() as s:
        await Ios2haClient(s, str(server.make_url("/"))).get_info()
    await server.close()


async def test_a_newer_api_version_is_refused_with_the_version_found():
    info = load_fixture_json("info")
    info["interfaces"]["api"] = 2
    server = await _serve([("GET", "/api/v1/info", _json(info))])
    async with aiohttp.ClientSession() as s:
        with pytest.raises(UnsupportedApi) as err:
            await Ios2haClient(s, str(server.make_url("/"))).get_info()
    await server.close()
    assert err.value.found == 2


async def test_a_404_on_info_means_the_api_is_off():
    server = await _serve([("GET", "/other", _json({}))])
    async with aiohttp.ClientSession() as s:
        with pytest.raises(ApiDisabled):
            await Ios2haClient(s, str(server.make_url("/"))).get_info()
    await server.close()


async def test_json_without_the_expected_shape_is_not_ios2ha():
    server = await _serve([("GET", "/api/v1/info", _json({"hello": "world"}))])
    async with aiohttp.ClientSession() as s:
        with pytest.raises(NotIos2ha):
            await Ios2haClient(s, str(server.make_url("/"))).get_info()
    await server.close()


async def test_nothing_listening_is_cannot_connect():
    async with aiohttp.ClientSession() as s:
        with pytest.raises(CannotConnect):
            await Ios2haClient(s, "http://127.0.0.1:9").get_info()


async def test_control_posts_the_value_and_a_press_posts_nothing():
    seen = []

    async def control(request):
        seen.append((request.match_info["name"], await request.text()))
        return web.json_response({"ok": True, "name": request.match_info["name"]})

    info = load_fixture_json("info")
    server = await _serve(
        [
            ("GET", "/api/v1/info", _json(info)),
            ("POST", "/api/v1/control/{name}", control),
        ]
    )
    async with aiohttp.ClientSession() as s:
        c = Ios2haClient(s, str(server.make_url("/")))
        await c.get_info()
        await c.post_control("interval_s", 600)
        await c.post_control("capture_now", NO_VALUE)
    await server.close()
    assert seen == [("interval_s", '{"value": 600}'), ("capture_now", "")]


async def test_a_rejected_control_raises_with_the_server_error():
    info = load_fixture_json("info")
    server = await _serve(
        [
            ("GET", "/api/v1/info", _json(info)),
            ("POST", "/api/v1/control/{name}", _json({"ok": False, "error": "out of range"}, 400)),
        ]
    )
    async with aiohttp.ClientSession() as s:
        c = Ios2haClient(s, str(server.make_url("/")))
        await c.get_info()
        with pytest.raises(ControlRejected) as err:
            await c.post_control("interval_s", 5)
    await server.close()
    assert err.value.status == 400 and err.value.error == "out of range"


@pytest.mark.parametrize(
    "hostile",
    [
        "@evil.example/x",  # the base becomes userinfo, evil.example the host
        "//evil.example/x",  # protocol-relative
        "https://evil.example/x",  # absolute
        "http://evil.example/x",
        "x/y",  # not absolute: silently relative to nothing
        "",
    ],
)
def test_a_path_that_leaves_the_configured_host_is_refused(hostile):
    """Every path but /info is named by the service, so they are network input.

    The link carries no authentication and no TLS, so anything able to answer as
    the service can choose these strings -- and concatenating them would let it
    move the request to a host of its choosing, with Home Assistant's network
    position and the answer rendered as a camera.
    """
    c = Ios2haClient(None, "http://camera-host.lan:8099")
    with pytest.raises(NotIos2ha):
        c.url(hostile)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/state", "http://camera-host.lan:8099/api/v1/state"),
        ("/api/v1/snapshot/still", "http://camera-host.lan:8099/api/v1/snapshot/still"),
        # Traversal cannot escape an origin, so it is normalised rather than refused.
        ("/a/../b", "http://camera-host.lan:8099/b"),
    ],
)
def test_a_path_on_the_configured_host_is_kept(path, expected):
    assert Ios2haClient(None, "http://camera-host.lan:8099").url(path) == expected
