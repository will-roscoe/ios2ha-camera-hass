"""The service's actions as Home Assistant actions.

Since 2.16.0 the service declares writes whose value is a JSON object -- the first
is `build_timelapse` -- in /objects, each with the fields a client needs to build a
form. Every one becomes `ios2ha_camera.<name>`: its schema and its form in Home
Assistant come from those fields, and a call goes to the service's control route
like every other write, so the service judges it and its refusal is the error.
Nothing here knows what a timelapse is.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .api import CannotConnect, ControlRejected
from .const import DOMAIN

ATTR_DEVICE_ID = "device_id"
_REGISTERED = f"{DOMAIN}_actions"


def _validator(field: dict) -> Any:
    kind = field.get("type")
    if kind == "int":
        return vol.All(vol.Coerce(int), vol.Range(min=field.get("min"), max=field.get("max")))
    if kind == "select":
        return vol.In(list(field.get("options", [])))
    return cv.string


def _selector(field: dict) -> dict:
    kind = field.get("type")
    if kind == "int":
        return {"number": {"min": field.get("min"), "max": field.get("max"), "mode": "box"}}
    if kind == "select":
        return {"select": {"options": list(field.get("options", []))}}
    if kind == "datetime":
        return {"datetime": {}}
    return {"text": {}}


def _schema(action: dict) -> vol.Schema:
    fields = {vol.Optional(k): _validator(f) for k, f in action.get("fields", {}).items()}
    fields[vol.Optional(ATTR_DEVICE_ID)] = cv.string
    return vol.Schema(fields)


def _description(action: dict) -> dict:
    """The form Home Assistant shows for the action, from the same fields."""
    fields = {
        k: {"name": k, "description": f.get("description", ""), "required": False,
            "selector": _selector(f), **({"example": f["default"]} if "default" in f else {})}
        for k, f in action.get("fields", {}).items()
    }
    fields[ATTR_DEVICE_ID] = {
        "name": "Camera", "required": False,
        "description": "Which camera, when more than one is set up.",
        "selector": {"device": {"integration": DOMAIN}},
    }
    return {"name": action["name"].replace("_", " ").capitalize(),
            "description": action.get("description", ""), "fields": fields}


def _zoned(text: Any) -> str:
    """A time from Home Assistant's form, which has no zone, in Home Assistant's
    own zone: the service would otherwise read it as its local time."""
    parsed = dt_util.parse_datetime(str(text))
    if parsed is None:
        raise ServiceValidationError(f"not a date and time: {text!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed.isoformat()


def _value(action: dict, data: dict) -> dict:
    out = {}
    for key, field in action.get("fields", {}).items():
        if key in data:
            out[key] = _zoned(data[key]) if field.get("type") == "datetime" else data[key]
    return out


def target(hass: HomeAssistant, device_id: str | None):
    """The coordinator of the camera a call is for."""
    loaded = [e for e in hass.config_entries.async_entries(DOMAIN)
              if e.state is ConfigEntryState.LOADED]
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        for entry in loaded:
            if device is not None and entry.entry_id in device.config_entries:
                return entry.runtime_data
        raise ServiceValidationError(f"{device_id} is not an ios2ha-camera device")
    if len(loaded) == 1:
        return loaded[0].runtime_data
    raise ServiceValidationError(
        "no camera is set up" if not loaded
        else "more than one camera is set up: choose one with device_id")


def _handler(hass: HomeAssistant, name: str):
    async def handle(call: ServiceCall) -> ServiceResponse:
        coordinator = target(hass, call.data.get(ATTR_DEVICE_ID))
        action = next((a for a in coordinator.actions if a.get("name") == name), None)
        if action is None:
            raise ServiceValidationError(f"this camera's service has no action {name}")
        try:
            body = await coordinator.client.post_control(name, _value(action, dict(call.data)))
        except ControlRejected as err:
            raise ServiceValidationError(f"{name}: {err.error}") from err
        except CannotConnect as err:
            raise HomeAssistantError(f"{name}: the service is unreachable ({err})") from err
        return body if call.return_response else None
    return handle


def async_register_actions(hass: HomeAssistant, coordinator) -> None:
    """Register every action this camera's service declares that is not registered
    yet. The first camera to declare an action shapes its form."""
    registered: set[str] = hass.data.setdefault(_REGISTERED, set())
    for action in coordinator.actions:
        name = action.get("name")
        if not name or name in registered:
            continue
        hass.services.async_register(DOMAIN, name, _handler(hass, name), schema=_schema(action),
                                     supports_response=SupportsResponse.OPTIONAL)
        async_set_service_schema(hass, DOMAIN, name, _description(action))
        registered.add(name)


def async_unregister_actions(hass: HomeAssistant) -> None:
    """Remove them all, with the last camera."""
    for name in hass.data.pop(_REGISTERED, set()):
        hass.services.async_remove(DOMAIN, name)
