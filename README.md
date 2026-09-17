# ios2ha-camera-hass

A Home Assistant integration (domain `ios2ha_camera`) for the
[ios2ha-camera](https://github.com/will-roscoe/ios2ha-camera) service, which turns an iPhone
running a camera app into a Home Assistant camera.

The service already exposes a versioned JSON API with live updates over server-sent events. This
integration builds every entity and camera from that API, so nothing has to be listed by hand and
an MQTT broker is not needed.

Installable through HACS as a custom repository. Being built; not yet released.
