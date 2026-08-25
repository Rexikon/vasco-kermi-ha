"""The Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VascoApiClient
from .const import CONF_SCAN_INTERVAL_SECONDS, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import VascoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.FAN, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vasco/Kermi Ventilation from a config entry."""
    session = async_get_clientsession(hass)
    client = VascoApiClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])

    scan_interval_seconds = entry.options.get(CONF_SCAN_INTERVAL_SECONDS)
    update_interval = (
        timedelta(seconds=scan_interval_seconds)
        if scan_interval_seconds
        else DEFAULT_SCAN_INTERVAL
    )

    coordinator = VascoCoordinator(hass, client, update_interval)
    # Raises ConfigEntryAuthFailed (bad credentials -> triggers reauth) or
    # ConfigEntryNotReady (network hiccup -> HA retries setup later) as
    # appropriate; both are handled by the DataUpdateCoordinator base class.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
