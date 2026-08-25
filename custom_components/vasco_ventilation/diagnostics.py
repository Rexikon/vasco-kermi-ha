"""Diagnostics support for the Vasco Ventilation integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import VascoCoordinator

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
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with secrets/identifiers redacted."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "account_configuration": async_redact_data(coordinator.data, TO_REDACT),
    }
