"""Timelapses in Home Assistant's Media panel, played through Home Assistant.

The service's video media descriptor names the state key that lists its items;
each item carries the url it is served at. The media source lists them and resolves
one to a path on this integration's view, which Home Assistant signs, so a browser
away from home plays it without ever reaching the service directly.
"""

import asyncio

from homeassistant.components import media_source
from homeassistant.setup import async_setup_component

from .conftest import SNAPSHOT

SERVICE_URL = "http://camera-host.lan:8099/api/v1/timelapse/last_24h.mp4"


async def _ready(hass, setup):
    assert await async_setup_component(hass, "media_source", {})
    return await setup([SNAPSHOT])


async def test_the_timelapses_are_listed_under_the_camera(hass, setup):
    entry = await _ready(hass, setup)
    root = await media_source.async_browse_media(hass, "media-source://ios2ha_camera")
    assert [c.title for c in root.children] == ["iPhone Camera"]
    camera = await media_source.async_browse_media(
        hass, f"media-source://ios2ha_camera/{entry.entry_id}"
    )
    assert [c.title for c in camera.children] == ["Timelapses"]
    folder = await media_source.async_browse_media(
        hass, f"media-source://ios2ha_camera/{entry.entry_id}/timelapse"
    )
    (item,) = folder.children
    assert item.can_play and "last_24h" in item.title and "141 frames" in item.title


async def test_one_resolves_to_this_integrations_view(hass, setup):
    entry = await _ready(hass, setup)
    played = await media_source.async_resolve_media(
        hass, f"media-source://ios2ha_camera/{entry.entry_id}/timelapse/last_24h", None
    )
    assert played.mime_type == "video/mp4"
    assert played.url == f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/last_24h.mp4"


async def test_the_view_streams_it_from_the_service_with_range(
    hass, setup, hass_client, aioclient_mock
):
    entry = await _ready(hass, setup)
    aioclient_mock.get(
        SERVICE_URL,
        status=206,
        content=b"0123456789",
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": "bytes 0-9/1000",
            "Accept-Ranges": "bytes",
        },
    )
    client = await hass_client()
    resp = await client.get(
        f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/last_24h.mp4",
        headers={"Range": "bytes=0-9"},
    )
    assert resp.status == 206
    assert await resp.read() == b"0123456789"
    assert resp.headers["Content-Range"] == "bytes 0-9/1000"
    assert resp.headers["Content-Type"] == "video/mp4"
    ((_, _, _, headers),) = aioclient_mock.mock_calls
    assert headers["Range"] == "bytes=0-9"


async def test_the_view_serves_only_what_the_catalogue_lists(hass, setup, hass_client):
    entry = await _ready(hass, setup)
    client = await hass_client()
    for path in (
        f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/missing.mp4",
        f"/api/ios2ha_camera/{entry.entry_id}/media/still/last_24h.mp4",
        "/api/ios2ha_camera/no-such-entry/media/timelapse/last_24h.mp4",
    ):
        assert (await client.get(path)).status == 404, path
    # A traversal is refused before it reaches the view: Home Assistant's own
    # security filter answers 400.
    traversal = f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/..%2Fx.mp4"
    assert (await client.get(traversal)).status in (400, 404)


async def test_the_view_needs_home_assistants_auth(hass, setup, hass_client_no_auth):
    entry = await _ready(hass, setup)
    client = await hass_client_no_auth()
    resp = await client.get(f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/last_24h.mp4")
    assert resp.status == 401


async def test_an_item_whose_url_leaves_the_service_is_refused(
    hass, setup, hass_client, aioclient_mock
):
    """The catalogue is network input: a url naming another host must not become a
    request from Home Assistant's network position."""
    entry = await _ready(hass, setup)
    import copy

    data = copy.deepcopy(entry.runtime_data.data)  # never the shared fixture
    data["timelapse_catalogue"]["items"]["last_24h"]["url"] = "//evil.example/x.mp4"
    entry.runtime_data.data = data
    client = await hass_client()
    resp = await client.get(f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/last_24h.mp4")
    assert resp.status == 404
    assert aioclient_mock.call_count == 0


async def test_a_viewer_leaving_mid_stream_is_not_an_error(
    hass, setup, hass_client, aioclient_mock, caplog
):
    """A video element drops requests all the time -- each seek -- so a write to a
    viewer who has gone must end the response quietly."""
    from unittest.mock import patch

    from aiohttp import web

    entry = await _ready(hass, setup)
    aioclient_mock.get(
        SERVICE_URL, status=200, content=b"x" * 200_000, headers={"Content-Type": "video/mp4"}
    )
    written = 0

    async def write(self, data):
        nonlocal written
        written += 1
        if written > 1:
            raise ConnectionResetError("Cannot write to closing transport")

    client = await hass_client()
    with patch.object(web.StreamResponse, "write", write):
        await client.get(f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/last_24h.mp4")
    assert "Error handling request" not in caplog.text
    assert "Traceback" not in caplog.text


class _Content:
    def __init__(self, chunks, fail_at=None):
        self.chunks, self.fail_at = chunks, fail_at

    async def iter_chunked(self, n):
        from aiohttp import ClientPayloadError

        for i, chunk in enumerate(self.chunks):
            if i == self.fail_at:
                raise ClientPayloadError("the service went mid-file")
            yield chunk


class _Upstream:
    def __init__(self, status=200, headers=None, content=None):
        self.status, self.headers = status, headers or {"Content-Type": "video/mp4"}
        self.content = content or _Content([b"0123456789"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, upstream=None, raises=None):
        self.upstream, self.raises, self.calls = upstream, raises, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        if self.raises:
            raise self.raises
        return self.upstream


async def _get_through(hass, setup, hass_client, session, **kw):
    from unittest.mock import patch

    entry = await _ready(hass, setup)
    client = await hass_client()
    with patch("custom_components.ios2ha_camera.views.async_get_clientsession", lambda h: session):
        resp = await client.get(
            f"/api/ios2ha_camera/{entry.entry_id}/media/timelapse/last_24h.mp4", **kw
        )
        try:
            body = await asyncio.wait_for(resp.read(), 5)
        except Exception as err:  # a cut connection, which is the point
            body = err
    return resp, body


async def test_a_redirect_is_not_followed(hass, setup, hass_client):
    """The origin check would mean nothing if the service could send Home
    Assistant on to another host."""
    session = _Session(_Upstream(status=302, headers={"Location": "http://evil.example/x"}))
    resp, _ = await _get_through(hass, setup, hass_client, session)
    assert resp.status == 502
    assert session.calls[0][1]["allow_redirects"] is False


async def test_a_long_video_is_not_cut_at_five_minutes(hass, setup, hass_client):
    session = _Session(_Upstream())
    await _get_through(hass, setup, hass_client, session)
    timeout = session.calls[0][1]["timeout"]
    assert timeout.total is None and timeout.sock_read and timeout.sock_connect


async def test_the_service_going_mid_file_ends_the_response(hass, setup, hass_client, caplog):
    """Headers are already out: the viewer must see the connection end, not wait
    for a Content-Length that will never arrive."""
    session = _Session(
        _Upstream(
            headers={"Content-Type": "video/mp4", "Content-Length": "1000"},
            content=_Content([b"x" * 100, b"y" * 100], fail_at=1),
        )
    )
    resp, body = await _get_through(hass, setup, hass_client, session)
    assert resp.status == 200 and isinstance(body, Exception)
    assert not isinstance(body, TimeoutError), "the viewer was left waiting"
    assert "Error handling request" not in caplog.text


async def test_a_service_that_does_not_answer_is_a_bad_gateway(hass, setup, hass_client):
    resp, _ = await _get_through(hass, setup, hass_client, _Session(raises=TimeoutError()))
    assert resp.status == 502
