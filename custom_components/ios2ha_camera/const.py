"""Constants for the ios2ha-camera integration."""

from homeassistant.const import Platform

DOMAIN = "ios2ha_camera"
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
CONF_URL = "url"
# The one path a client may hardcode; everything else comes from its routes map.
INFO_PATH = "/api/v1/info"
SUPPORTED_API = 1
# Entity ids are `<domain>.ios2ha_camera_<object_id>`, the same as MQTT discovery
# produces, so automations survive the migration.
OBJECT_ID_PREFIX = "ios2ha_camera"
STORAGE_VERSION = 1
REQUEST_TIMEOUT = 10
# Reconnect backoff for the event stream, in seconds.
RECONNECT_MIN = 1.0
RECONNECT_MAX = 60.0
