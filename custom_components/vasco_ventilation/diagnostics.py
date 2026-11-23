"""Diagnostics support for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import VascoConfigEntry

TO_REDACT = {
    "password",
    "email",
    "userToken",
    "bridgeToken",
    "mqttPassword",
    "mqttUserName",
    "mqttClientId",
    "serial",
    "macAddress",
    "roomId",
    # Location data: users attach diagnostics to public GitHub issues.
    "externalIP",
    "weatherAndGeoData",
    "city",
    "location",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VascoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with secrets/identifiers redacted."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        # Number of bridges the live-updates connection is currently up for.
        "live_connections": len(coordinator.live_connected),
        "account_configuration": async_redact_data(coordinator.data, TO_REDACT),
    }
