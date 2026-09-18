# ios2ha-camera for Home Assistant

A Home Assistant integration for the
[ios2ha-camera](https://will-roscoe.github.io/ios2ha-camera/) service, which turns an
iPhone into a camera and a set of controls. It builds every entity from the
service's own description of itself over the JSON API, and keeps them live over
one event stream, so nothing is polled and nothing is listed twice: an entity
added to the service appears here without an update to this integration.

It is the second of two supported ways to connect the service to Home Assistant.
The other is MQTT discovery plus hand-made Generic Camera entries, which stays
supported. Both produce the same entity ids, so moving between them does not
break dashboards or automations.

## Requirements

- Home Assistant **2026.9.1** or newer.
- An ios2ha-camera service **2.6.0** or newer, with `EXPOSE_API` on (the default).
  The screenshot camera needs **2.7.0** or newer.
- The service reachable from Home Assistant on its `LIVE_PORT`, e.g.
  `http://camera-host.lan:8099`.

## Install

Through HACS, as a custom repository:

1. HACS → three-dot menu → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Find **ios2ha-camera** in HACS, install it, and restart Home Assistant.

## Configure

**Settings → Devices & services → Add integration → ios2ha-camera**, then enter
the address of the service, for example `http://camera-host.lan:8099`. A bare
`camera-host.lan:8099` is accepted and read as `http://`. There is nothing else
to fill in: the API has no authentication.

If the address does not work, the form says which of four things went wrong:

| Message | What it means |
| --- | --- |
| Could not reach an ios2ha-camera service at that address | Nothing answered. Check the host, the port and the network. |
| Something answered, but it is not an ios2ha-camera service | Something is listening on that port, but it is not this service. |
| The service is running with `EXPOSE_API=false` | The service is there; its JSON API is switched off. Turn it on and restart it. |
| This service speaks API version *n* | The service is newer than this integration. Update the integration. |

## What you get

One device, named after the service, carrying every entity the service
describes: sensors, binary sensors, numbers, selects, switches, buttons and
cameras. Entity ids are `<domain>.ios2ha_camera_<object_id>` — identical to the
ones MQTT discovery creates.

Cameras come from what the service actually serves over HTTP:

- **still** — the camera snapshot. Free: it does not wake or hold the phone.
- **live** and **stacked** — MJPEG streams, proxied only while someone is
  watching. Their thumbnails come from the still, so a dashboard full of camera
  cards does not hold the phone open.
- **screenshot** — the phone's own screen, as the **Phone screenshot** button
  last captured it. Also free: viewing it never takes a new one, which is the
  button's job. It shows as unavailable until the button has been pressed once.

Updates are pushed over one long-lived event stream. Nothing polls. If the
stream drops, the entities go unavailable and the integration reconnects with a
backoff; the first message after a reconnect is a full snapshot, so the state
you see is never a stale partial one.

## Moving from MQTT

Home Assistant will not give an entity id to a second entity while the first
still holds it, so the order matters:

1. **Turn MQTT off.** Set `EXPOSE_MQTT=false` on the service and restart it. At
   startup it clears its retained discovery topics and its retained availability
   message, which deletes the MQTT entities and releases their ids. Check the
   entities have actually gone from Home Assistant before carrying on — if the
   broker was unreachable, the service's log says so and nothing was cleared.
2. **Add this integration**, as above. Its entities take the same object ids, and
   so the same entity ids.
3. **Remove any hand-made Generic Camera entries** pointed at `/live`,
   `/live/stacked` or `/still.jpg`, once this integration's cameras are working.
   Until then they keep working: those paths are permanent.

## Security

The service's JSON API has **no authentication** and no TLS, by design, and this
integration does not add any. Anyone who can reach the port can read the state
and write the controls. Keep it on a network you trust, and do not forward the
port.

Because of that, this integration treats everything the service says as input
rather than fact. The service names its own paths — the routes map in
`/api/v1/info` and each media descriptor's `url` — and those are checked to
resolve to the address you configured before any request is made. A path that
would move the request to another host is refused and logged, so something able
to answer as the service cannot use Home Assistant's network position to reach
somewhere else, or have its own content rendered as your camera.

## Known gaps

- **The screenshot camera needs service 2.7.0 or newer.** Before that the image
  was published only as a retained MQTT topic, with no HTTP route, and this
  integration skips any camera the service offers no route for rather than point
  one at a path that does not exist.
- **No HLS or WebRTC.** The streams are MJPEG. The integration does not
  advertise Home Assistant's stream feature, which would promise formats the
  service cannot yet produce.

## Licence

Apache-2.0, the same as the service.
