"""Enough to debug a link without leaking where the service lives."""

from collections import Counter

from homeassistant.components.diagnostics import async_redact_data

TO_REDACT = {"url", "configuration_url"}


async def async_get_config_entry_diagnostics(hass, entry):
    c = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "info": async_redact_data(c.info, TO_REDACT),
        "connected": c.connected,
        "objects_version": c.objects_version,
        "domains": dict(Counter(d.get("domain") for d in c.objects)),
        "media": [m.get("id") for m in c.media],
        # The flat state carries measurements only; no credential exists in it.
        "state": c.data,
    }
